from pyteal import *
from pyteal.ast.bytes import Bytes
import sys
sys.path.insert(0, '..')
from pyteal_helpers import program


def approval():
    # company keys that would be retrieved
    vault_id_key = Bytes("vault_id")

    # vault keys
    vault_name_key = Bytes("vault_name")  # byteslice
    vault_wallet_key = Bytes("vault_wallet")  # byteslice
    company_id_key = Bytes("company_id")  # uint64
    company_wallet_key = Bytes("company_wallet")  # byteslice
    coins_key = Bytes("coins_id")  # uint64

    # operation
    coins_optin = Bytes("connect_company_and_optIn_to_coins")

    # initialize vault
    @Subroutine(TealType.none)
    def on_create():
        return Seq(
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            Assert(
                # vault name
                Txn.application_args.length() == Int(1),
            ),
            App.globalPut(vault_name_key, Txn.application_args[0]),
            App.globalPut(vault_wallet_key,
                          Global.current_application_address()),
            App.globalPut(company_id_key, Int(0)),
            App.globalPut(company_wallet_key, Bytes("")),
            App.globalPut(coins_key, Int(0)),
            Approve(),
        )

    # asset optIn
    @Subroutine(TealType.none)
    def optIn_assets(asset_id):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: asset_id,
                    TxnField.asset_receiver: Global.current_application_address(),
                    TxnField.asset_amount: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),

        )

    # one-time function that let the vault connect to a company and optIn into the coins ID
    @Subroutine(TealType.none)
    def accept_company_and_optIn_coins():
        company_wallet = ScratchVar(TealType.bytes)
        company_id = ScratchVar(TealType.uint64)
        coins_id = ScratchVar(TealType.uint64)
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            company_wallet.store(Txn.sender()),
            company_id.store(Txn.applications[1]),
            coins_id.store(Txn.assets[0]),
            Assert(
                And(
                    # make sure the vault has no connected with any company
                    App.globalGet(company_id_key) == Int(0),
                    App.globalGet(company_wallet_key) == Bytes(""),
                    # Make sure the vault has not accepted any coins
                    App.globalGet(coins_key) == Int(0),
                    # operation
                    Txn.application_args.length() == Int(1),
                ),
            ),
            App.globalPut(company_id_key, company_id.load()),
            App.globalPut(company_wallet_key, company_wallet.load()),
            optIn_assets(coins_id.load()),
            App.globalPut(coins_key, coins_id.load()),
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
                    Txn.application_args[0] == coins_optin,
                    accept_company_and_optIn_coins(),
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
    compiled = compileTeal(clear(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)
