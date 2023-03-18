import sys
sys.path.insert(0, '..')
from pyteal.ast.bytes import Bytes
from pyteal import *
from pyteal_helpers import program


def approval():

    # company key information
    company_name_key = Bytes("company_name")  # byteslice
    company_wallet_key = Bytes("company_wallet")  # byteslice
    coins_key = Bytes("coins_id")  # uint64
    shares_key = Bytes("shares_id")  # uint64
    number_of_founders_key = Bytes("number_of_founder(s)")  # uint64
    # unallocated_shares_key = Bytes("unallocated_shares")  # uint64
    shares_total_key = Bytes("shares_total")  # uint64
    founders_added = Bytes("founders_added")
    # shares_remain_key = Bytes("remain_shares")  # uint64
    vault_id_key = Bytes("vault_id")  # uint64
    vault_wallet_key = Bytes("vault_wallet")  # byteslices

    # operation
    op_on_create_add_founders = Bytes("add_founders")
    op_on_create_mint_coins = Bytes("mint_coins")
    op_on_create_mint_shares = Bytes("mint_shares")
    op_on_create_deposit_coins = Bytes("deposit_coins")
    op_on_create_distribute_shares = Bytes("distribute_shares")
    op_post_create_distribute_shares = Bytes("distribute_remain_shares")

    # Exp
    sender = Bytes("sender")
    receiver = Bytes("receiver")
    founder = Bytes("founder")

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
        return Seq(
            Assert(
                # company name, total founders
                Txn.application_args.length() == Int(2)
            ),
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
            # number of founders
            App.globalPut(number_of_founders_key,
                          Btoi(Txn.application_args[1])),
            # shares total
            App.globalPut(shares_total_key, Int(0)),
            # indicate the founders setting operation
            App.globalPut(founders_added, Int(0)),
        )

    # add founders
    @ Subroutine(TealType.none)
    def on_create_add_founders():
        total_founders = ScratchVar(TealType.uint64)
        added_founders = ScratchVar(TealType.uint64)
        i = ScratchVar(TealType.uint64)
        return Seq(
            total_founders.store(App.globalGet(number_of_founders_key)),
            added_founders.store(App.globalGet(founders_added)),
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            Assert(
                And(
                    (App.globalGet(founders_added) + Txn.application_args.length() - Int(1)) <= total_founders.load(),
                    # operation, founder address1 ... founder addressX (up to 11)
                    Txn.application_args.length() <= Int(11),
                ),
            ),
            For(i.store(added_founders.load() + Int(1)), i.load() < (added_founders.load() + Txn.application_args.length()), i.store(i.load() + Int(1))).Do(
                App.globalPut(convert_uint_to_bytes(i.load()),
                              Txn.application_args[i.load() - added_founders.load()]),
            ),
            App.globalPut(founders_added, (Txn.application_args.length() + added_founders.load() - Int(1))),
            Approve(),
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
    def create_tokens(asset_name, asset_unit_name, asset_total, asset_decimal, asset_reserve_status):
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
                        TxnField.config_asset_default_frozen: Int(0),
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
                        TxnField.config_asset_default_frozen: Int(0),
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
    def on_create_mint_coins():
        vault_id = ScratchVar(TealType.uint64)
        vault_wallet = ScratchVar(TealType.bytes)
        coins_id = ScratchVar(TealType.uint64)
        coins_name = ScratchVar(TealType.bytes)
        coins_unit_name = ScratchVar(TealType.bytes)
        coins_amount = ScratchVar(TealType.uint64)
        coins_decimal = ScratchVar(TealType.uint64)
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
                    Txn.application_args.length() == Int(5),
                )
            ),
            # mint coins
            create_tokens(coins_name.load(), coins_unit_name.load(), coins_amount.load(
            ), coins_decimal.load(), asset_reserve_status.load()),
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
    def on_create_mint_shares():
        shares_id = ScratchVar(TealType.uint64)
        shares_name = ScratchVar(TealType.bytes)
        shares_unit_name = ScratchVar(TealType.bytes)
        shares_amount = ScratchVar(TealType.uint64)
        shares_decimal = ScratchVar(TealType.uint64)
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
            shares_amount.store(Btoi(Txn.application_args[3])),
            shares_decimal.store(Btoi(Txn.application_args[4])),
            asset_reserve_status.store(Int(0)),
            Assert(
                And(
                    # make sure the company has not created shares
                    App.globalGet(shares_key) == Int(0),
                    # operation, company name, shares amount including decimal, shares unit name, shares decimal, default frozen
                    Txn.application_args.length() == Int(5),
                )
            ),
            # mint shares
            create_tokens(shares_name.load(), shares_unit_name.load(), shares_amount.load(
            ), shares_decimal.load(), asset_reserve_status.load()),
            # shares id
            shares_id.store(InnerTxn.created_asset_id()),
            App.globalPut(shares_key, shares_id.load()),
            # shares amount
            App.globalPut(shares_total_key, shares_amount.load()),
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
                    [Or(role == Bytes("sender"),
                        role == Bytes("founder")), accountAssetBalance.value()],
                    [role == Bytes("receiver"),
                     accountAssetBalance.hasValue()],
                )
            )
        )

    # one-time function distribute shares to founders respectively
    @Subroutine(TealType.none)
    def on_create_distribute_shares():
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
            shares_total.store(Int(0)),
            # get the shares ID from the global key of shares
            shares_id.store(Txn.assets[0]),
            # get the remain amount of shares that is held by the company
            available_shares.store(check_assets_holding(
                sender, Global.current_application_address(), shares_id.load())),
            # get the total shares distributed to founders
            For(i.store(Txn.accounts.length() + Int(1)), i.load() <= Txn.accounts.length() * Int(2), i.store(i.load()+Int(1))).Do(
                shares_total.store(shares_total.load() + \
                                   Btoi(Txn.application_args[i.load()]))
            ),
            Assert(
                And(
                    # make sure the transfered asset id equals to the shares ID
                    shares_id.load() == App.globalGet(shares_key),
                    # make sure the company created enough shares to distribute
                    available_shares.load() >= shares_total.load(),
                    # operation, id of each founder, shares for each founder
                    Txn.application_args.length() == (Txn.accounts.length() * Int(2)) + Int(1),
                )
            ),
            # make sure each founder has opted in but not received shares
            For(i.store(Int(1)), i.load() <= Txn.accounts.length(), i.store(i.load() + Int(1))).Do(
                Assert(
                    App.globalGet(
                        Txn.application_args[i.load()]) == Txn.accounts[i.load()],
                    check_assets_holding(
                        founder, Txn.accounts[i.load()], shares_id.load()) == Int(0),
                )
            ),
            # send shares
            For(i.store(Int(1)), i.load() <= Txn.accounts.length(), i.store(i.load() + Int(1))).Do(
                company_send_tokens(shares_id.load(), Btoi(Txn.application_args[i.load(
                ) + Txn.accounts.length()]), Txn.accounts[i.load()])
            ),
            Approve(),
        )

    # Send coins to vault wallet
    @ Subroutine(TealType.none)
    def on_create_deposit_coins():
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

    # post create function distributing shares to other addresses
    @Subroutine(TealType.none)
    def post_create_distribute_shares():
        receiver_addr = ScratchVar(TealType.bytes)
        shares_id = ScratchVar(TealType.uint64)
        shares_amount = ScratchVar(TealType.uint64)
        available_shares = ScratchVar(TealType.uint64)
        return Seq(
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            # get the receiver's address
            receiver_addr.store(Txn.accounts[1]),
            # get the distributing amount of shares
            shares_amount.store(Btoi(Txn.application_args[1])),
            # get the shares ID from the global key of shares
            shares_id.store(Txn.assets[0]),
            # get the remain amount of shares that is held by the company
            available_shares.store(check_assets_holding(
                sender, Global.current_application_address(), shares_id.load())),
            Assert(
                And(
                    # make sure the transfered asset id equals to the shares ID
                    shares_id.load() == App.globalGet(shares_key),
                    # make sure the company created enough shares to distribute
                    available_shares.load() >= shares_amount.load(),
                    # make sure the receiver has opted in
                    check_assets_holding(
                        receiver, receiver_addr.load(), shares_id.load()),
                    # operation, amount of shares
                    Txn.application_args.length() == Int(2),
                )
            ),
            # send shares
            company_send_tokens(shares_id.load(), shares_amount.load(), receiver_addr.load()),
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
                    Txn.application_args[0] == op_on_create_add_founders,
                    on_create_add_founders(),
                ],
                [
                    Txn.application_args[0] == op_on_create_mint_coins,
                    on_create_mint_coins(),
                ],
                [
                    Txn.application_args[0] == op_on_create_mint_shares,
                    on_create_mint_shares(),
                ],
                [
                    Txn.application_args[0] == op_on_create_deposit_coins,
                    on_create_deposit_coins(),
                ],
                [
                    Txn.application_args[0] == op_on_create_distribute_shares,
                    on_create_distribute_shares(),
                ],
                [
                    Txn.application_args[0] == op_post_create_distribute_shares,
                    post_create_distribute_shares(),
                ],
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('company_step_03.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)

with open("company_step_03_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)
