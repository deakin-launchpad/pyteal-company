from pyteal import *
from pyteal.ast.bytes import Bytes
from pyteal_helpers import program


def approval():
    # company keys that would be retrieved
    vault_id_key = Bytes("vault_id")

    # vault keys
    vault_name_key = Bytes("vault_name")  # byteslice
    vault_wallet_key = Bytes("vault_wallet")  # byteslice
    company_id_key = Bytes("company_id")  # uint64
    company_wallet_key = Bytes("company_wallet")  # byteslice
    verified_by_company_key = Bytes("verified_by_company")  # uint64
    coins_key = Bytes("coins_id")  # uint64

    # operation
    binding_request = Bytes("binding_request")

    # get global value of other applications
    @Subroutine(TealType.anytype)
    def get_global_value(appId, key):
        app_global_value = App.globalGetEx(appId, key)
        return Seq(
            app_global_value,
            Return(
                app_global_value.value()
            )
        )

    # initialize vault
    @Subroutine(TealType.none)
    def on_create():
        company_id = ScratchVar(TealType.uint64)
        company_wallet = ScratchVar(TealType.bytes)
        return Seq(
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            # company id passed through foreign app id, Txn.app[0] == Int(0) when initializ an application
            company_id.store(Txn.applications[1]),
            # company wallet passed through Txn account
            company_wallet.store(Txn.accounts[1]),
            Assert(
                And(
                    # vault name
                    Txn.application_args.length() == Int(1),
                    # make sure the company wallet in Txn account equals to the company wallet retreived from the company app
                    get_global_value(company_id.load(), company_wallet_key) == company_wallet.load(),
                    # make sure the company app is not bound with any vault
                    get_global_value(company_id.load(), vault_id_key) == Int(0),
                    get_global_value(company_id.load(), vault_wallet_key) == Bytes(""),
                ),
            ),
            App.globalPut(vault_name_key, Txn.application_args[0]),
            App.globalPut(vault_wallet_key,
                          Global.current_application_address()),
            App.globalPut(company_id_key, company_id.load()),
            App.globalPut(company_wallet_key, company_wallet.load()),
            # waiting for a verification from the company
            App.globalPut(verified_by_company_key, Int(0)),
            # coins that will be transfered from the company
            App.globalPut(coins_key, Int(0)),
            Approve(),
        )

    # create assets (coins or shares)
    @Subroutine(TealType.none)
    def app_call_company_bind_vault(company_id, vault_id, vault_wallet):
        operation = ScratchVar(TealType.bytes)
        return Seq(
            operation.store(Bytes("str:bind_vault")),
            InnerTxnBuilder.Begin(),
            # application call that binds company with the newly created vault
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: company_id,
                    TxnField.on_completion: OnComplete.NoOp,
                    TxnField.accounts: [vault_wallet],
                    TxnField.application_args: [Bytes("bind_vault")],
                    TxnField.applications: [vault_id],
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    # one-time function requst a verification from the company
    @Subroutine(TealType.none)
    def let_company_bind_vault():
        company_id = ScratchVar(TealType.uint64)
        vault_id = ScratchVar(TealType.uint64)
        vault_wallet = ScratchVar(TealType.bytes)
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            company_id.store(App.globalGet(company_id_key)),
            vault_id.store(Global.current_application_id()),
            vault_wallet.store(Global.current_application_address()),
            Assert(
                And(
                    # make sure the vault has not been verified and accepted by the company
                    App.globalGet(verified_by_company_key) == Int(0),
                    # make sure the foreign app id equals to the company id
                    Txn.applications[1] == company_id.load(),
                    # operation
                    Txn.application_args.length() == Int(1),
                ),
            ),
            # application call to let the company put vault key information
            app_call_company_bind_vault(company_id.load(), vault_id.load(
            ), vault_wallet.load()),
            # indicates that the vault has been verified and accepted by a company
            App.globalPut(verified_by_company_key, Int(1)),
            Approve(),
        )

    return program.event(
        init=Seq(
            on_create(),
            Approve(),
        ),
        no_op=Seq(
            Cond(
                [
                    Txn.application_args[0] == binding_request,
                    let_company_bind_vault(),
                ],
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('vault.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)

with open("vault_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application, version=MAX_PROGRAM_VERSION)
    f.write(compiled)
