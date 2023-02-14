import sys
sys.path.insert(0, '..')
from pyteal_helpers import program
from pyteal import *
from pyteal.ast.bytes import Bytes


def approval():

    # company key information
    company_name_key = Bytes("company_name")  # byteslice
    company_wallet_key = Bytes("company_wallet")  # byteslice
    coins_key = Bytes("coins_id")  # uint64
    shares_key = Bytes("shares_id")  # uint64
    founder_key = Bytes("founder")  # byteslice
    number_of_founders_key = Bytes("number_of_founder")  # uint64
    unallocated_shares_key = Bytes("unallocated_shares")  # uint64
    shares_total_key = Bytes("shares_total")  # uint64
    vault_id_key = Bytes("vault_id")  # uint64
    vault_wallet_key = Bytes("vault_wallet")  # byteslices

    # operation
    op_mint_coins = Bytes("mint_coins")
    op_mint_shares = Bytes("mint_shares")
    op_deposit_coins = Bytes("deposit_coins")
    op_distribute_shares = Bytes("distribute_shares")

    # Exp
    sender = Bytes("sender")
    receiver = Bytes("receiver")

    @Subroutine(TealType.bytes)
    def convert_uint_to_bytes(arg):

        string = ScratchVar(TealType.bytes)
        num = ScratchVar(TealType.uint64)
        digit = ScratchVar(TealType.uint64)

        return If(
            arg == Int(0),
            Bytes("0"),
            Seq([
                string.store(Bytes("")),
                For(num.store(arg), num.load() > Int(0), num.store(num.load() / Int(10))).Do(
                    Seq([
                        digit.store(num.load() % Int(10)),
                        string.store(
                            Concat(
                                Substring(
                                    Bytes('0123456789'),
                                    digit.load(),
                                    digit.load() + Int(1)
                                ),
                                string.load()
                            )
                        )
                    ])

                ),
                string.load()
            ])
        )

    # initialize company
    @Subroutine(TealType.none)
    def on_create():
        i = ScratchVar(TealType.uint64)
        shares_total = ScratchVar(TealType.uint64)
        return Seq(
            Assert(
                # company name, amount of shares a founder will be holding..., unallocated shares
                Txn.application_args.length() == Txn.accounts.length() + Int(2)
            ),
            shares_total.store(Int(0)),
            # commpany name
            App.globalPut(company_name_key, Txn.application_args[0]),
            # company wallet
            App.globalPut(company_wallet_key,
                          Global.current_application_address()),
            # company coins
            App.globalPut(coins_key, Int(0)),
            # company shares
            App.globalPut(shares_key, Int(0)),
            # company vault
            App.globalPut(vault_id_key, Int(0)),
            # vault wallet
            App.globalPut(vault_wallet_key, Bytes("")),
            # company founders holding shares
            For(i.store(Int(1)), i.load() <= Txn.accounts.length(), i.store(i.load() + Int(1))).Do(
                App.globalPut(Txn.accounts[(i.load())], Btoi(
                    Txn.application_args[i.load()])),
                shares_total.store(shares_total.load() + \
                                   Btoi(Txn.application_args[i.load()])),
            ),
            # number of founders
            App.globalPut(number_of_founders_key, (i.load() - Int(1))),
            # unallocated shares
            App.globalPut(unallocated_shares_key, Btoi(
                Txn.application_args[i.load()])),
            shares_total.store(shares_total.load() + \
                               Btoi(Txn.application_args[i.load()])),
            # total shares will be created
            App.globalPut(shares_total_key, shares_total.load())
        )

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

    @Subroutine(TealType.none)
    def create_tokens(asset_name, asset_unit_name, asset_total, asset_decimal, asset_default_frozen, asset_reserve_status):
        return Seq(
            InnerTxnBuilder.Begin(),
            If(asset_reserve_status == Int(1))
            .Then(
                # create an asset that needs a reserve account
                InnerTxnBuilder.SetFields(
                    {
                        TxnField.type_enum: TxnType.AssetConfig,
                        TxnField.config_asset_name: asset_name,
                        TxnField.config_asset_unit_name: asset_unit_name,
                        TxnField.config_asset_total: asset_total,
                        TxnField.config_asset_decimals: asset_decimal,
                        TxnField.config_asset_default_frozen: asset_default_frozen,
                        TxnField.config_asset_reserve: Txn.accounts[1],
                    }
                ),
            )
            .Else(
                # create an asset that does not need a reserve account
                InnerTxnBuilder.SetFields(
                    {
                        TxnField.type_enum: TxnType.AssetConfig,
                        TxnField.config_asset_name: asset_name,
                        TxnField.config_asset_unit_name: asset_unit_name,
                        TxnField.config_asset_total: asset_total,
                        TxnField.config_asset_decimals: asset_decimal,
                        TxnField.config_asset_default_frozen: asset_default_frozen,
                    }
                ),
            ),
            InnerTxnBuilder.Submit(),
        )

    # connect to a vault and let it OptIn to the coins ID
    @Subroutine(TealType.none)
    def vault_connect_and_optIn_coins(vault_id, coins_id):
        operation = ScratchVar(TealType.bytes)
        return Seq(
            operation.store(Bytes("connect_company_and_optIn_to_coins")),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: vault_id,
                    TxnField.on_completion: OnComplete.NoOp,
                    TxnField.application_args: [operation.load()],
                    TxnField.assets: [coins_id],
                    TxnField.applications: [Global.current_application_id()],
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    # one-time function create coins and reserve the coins
    @Subroutine(TealType.none)
    def mint_coins():
        vault_id = ScratchVar(TealType.uint64)
        vault_wallet = ScratchVar(TealType.bytes)
        coins_id = ScratchVar(TealType.uint64)
        coins_name = ScratchVar(TealType.bytes)
        coins_unit_name = ScratchVar(TealType.bytes)
        coins_amount = ScratchVar(TealType.uint64)
        coins_decimal = ScratchVar(TealType.uint64)
        coins_default_frozen = ScratchVar(TealType.uint64)
        asset_reserve_status = ScratchVar(TealType.uint64)
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            vault_id.store(Txn.applications[1]),
            vault_wallet.store(Txn.accounts[1]),
            coins_name.store(Txn.application_args[1]),
            coins_unit_name.store(Txn.application_args[2]),
            coins_amount.store(Btoi(Txn.application_args[3])),
            coins_decimal.store(Btoi(Txn.application_args[4])),
            coins_default_frozen.store(Btoi(Txn.application_args[5])),
            asset_reserve_status.store(Int(1)),
            Assert(
                And(
                    # make sure the company has not created any crypto
                    App.globalGet(coins_key) == Int(0),
                    # make sure that the company has no vault connected
                    App.globalGet(vault_wallet_key) == Bytes(""),
                    App.globalGet(vault_id_key) == Int(0),
                    # make sure the vault wallet belongs to the vault id
                    get_global_value(
                        vault_id.load(), vault_wallet_key) == vault_wallet.load(),
                    # operation, coins name, coins unit name, coins amount including decimal numbers, coins decimal, default frozen
                    Txn.application_args.length() == Int(6),
                )
            ),
            # mint coins
            create_tokens(coins_name.load(), coins_unit_name.load(), coins_amount.load(
            ), coins_decimal.load(), coins_default_frozen.load(), asset_reserve_status.load()),
            # coins id
            coins_id.store(InnerTxn.created_asset_id()),
            # let the vault store and optin to the coins
            vault_connect_and_optIn_coins(vault_id.load(), coins_id.load()),
            # put coins, vault ID and vault address
            App.globalPut(coins_key, coins_id.load()),
            App.globalPut(vault_id_key, vault_id.load()),
            App.globalPut(vault_wallet_key, vault_wallet.load()),
            Approve(),
        )

    # one-time function create shares
    @Subroutine(TealType.none)
    def mint_shares():
        shares_id = ScratchVar(TealType.uint64)
        shares_name = ScratchVar(TealType.bytes)
        shares_unit_name = ScratchVar(TealType.bytes)
        shares_amount = ScratchVar(TealType.uint64)
        shares_decimal = ScratchVar(TealType.uint64)
        shares_default_frozen = ScratchVar(TealType.uint64)
        asset_reserve_status = ScratchVar(TealType.uint64)
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            shares_name.store(Txn.application_args[1]),
            shares_unit_name.store(Txn.application_args[2]),
            shares_amount.store(App.globalGet(shares_total_key)),
            shares_decimal.store(Btoi(Txn.application_args[3])),
            shares_default_frozen.store(Btoi(Txn.application_args[4])),
            asset_reserve_status.store(Int(0)),
            Assert(
                And(
                    # make sure the company has not created shares
                    App.globalGet(shares_key) == Int(0),
                    # operation, company name, shares unit name, shares decimal, default frozen
                    Txn.application_args.length() == Int(5),
                )
            ),
            # mint shares
            create_tokens(shares_name.load(), shares_unit_name.load(), shares_amount.load(
            ), shares_decimal.load(), shares_default_frozen.load(), asset_reserve_status.load()),
            # shares id
            shares_id.store(InnerTxn.created_asset_id()),
            App.globalPut(shares_key, shares_id.load()),
            Approve(),
        )

    # send assets
    @Subroutine(TealType.none)
    def company_send_tokens(asset_id, amount, receiver):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: asset_id,
                    TxnField.asset_receiver: receiver,
                    TxnField.asset_amount: amount,
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    # check assets holding information, return asset amount if the role is a sender but optIn status if the rols is a reciever
    @Subroutine(TealType.uint64)
    def check_assets_holding(role, accountAddr, asset_id):
        accountAssetBalance = AssetHolding.balance(accountAddr, asset_id)
        return Seq(
            accountAssetBalance,
            Return(
                Cond(
                    [role == Bytes("sender"), accountAssetBalance.value()],
                    [role == Bytes("receiver"),
                     accountAssetBalance.hasValue()],
                )
            )
        )

    # one-time function distribute shares to founders respectively
    @Subroutine(TealType.none)
    def distribute_shares():
        founders_number = ScratchVar(TealType.uint64)
        shares_id = ScratchVar(TealType.uint64)
        shares_total = ScratchVar(TealType.uint64)
        available_shares = ScratchVar(TealType.uint64)
        i = ScratchVar(TealType.uint64)
        return Seq(
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            program.check_rekey_zero(Txn.application_args.length()),
            # get the shares ID from the global key of shares
            shares_id.store(Txn.assets[0]),
            # get the total number of shares that is held by the company
            available_shares.store(check_assets_holding(
                sender, Global.current_application_address(), shares_id.load())),
            # get the total shares recorded by the company
            shares_total.store(App.globalGet(shares_total_key)),
            # get the number of founders from the global key
            founders_number.store(App.globalGet(number_of_founders_key)),
            Assert(
                And(
                    # make sure the transfered asset id equals to the shares ID
                    shares_id.load() == App.globalGet(shares_key),
                    # make sure the company created enough shares to distribute
                    available_shares.load() == shares_total.load(),
                    # operation
                    Txn.application_args.length() == Int(1),
                    # Txn.application_args.length() == founders_number.load() + Int(1),
                    Txn.accounts.length() == founders_number.load(),
                )
            ),
            # Check founder addresses and optin status
            For(i.store(Int(1)), i.load() <= founders_number.load(), i.store(i.load() + Int(1))).Do(
                Assert(
                    And(
                        App.globalGet(Txn.accounts[i.load()]) >= Int(0),
                        check_assets_holding(
                            receiver, Txn.accounts[i.load()], shares_id.load()),
                    ),
                )
            ),
            # send shares
            For(i.store(Int(1)), i.load() <= founders_number.load(), i.store(i.load() + Int(1))).Do(
                company_send_tokens(shares_id.load(), App.globalGet(
                    Txn.accounts[i.load()]), Txn.accounts[i.load()])
            ),
            Approve(),
        )

    # Send coins to vault wallet
    @ Subroutine(TealType.none)
    def deposit_coins():
        vault_wallet = ScratchVar(TealType.bytes)
        coins_id = ScratchVar(TealType.uint64)
        coins_amount = ScratchVar(TealType.uint64)
        return Seq(
            vault_wallet.store(Txn.accounts[1]),
            coins_id.store(Txn.assets[0]),
            coins_amount.store(check_assets_holding(
                sender, Global.current_application_address(), coins_id.load())),
            Assert(
                And(
                    # check the coins ID
                    App.globalGet(coins_key) == coins_id.load(),
                    # check vault wallet
                    App.globalGet(vault_wallet_key) == vault_wallet.load(),
                    # check optin status of the vault
                    check_assets_holding(
                        receiver, vault_wallet.load(), coins_id.load()),
                    # coins_amount cannot be 0
                    coins_amount.load() >= Int(0),
                    # operation
                    Txn.application_args.length() == Int(1),
                ),
            ),
            company_send_tokens(
                coins_id.load(), coins_amount.load(), vault_wallet.load()),
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
                    Txn.application_args[0] == op_mint_coins,
                    mint_coins(),
                ],
                [
                    Txn.application_args[0] == op_mint_shares,
                    mint_shares(),
                ],
                [
                    Txn.application_args[0] == op_deposit_coins,
                    deposit_coins(),
                ],
                [
                    Txn.application_args[0] == op_distribute_shares,
                    distribute_shares(),
                ],
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('company_step_02.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)

with open("company_step_02_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)
