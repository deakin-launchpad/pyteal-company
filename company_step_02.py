from pyteal import *
from pyteal.ast.bytes import Bytes
from pyteal_helpers import program


def approval():

    # company name
    company_name = Bytes("Test01")

    # company key information
    company_name_key = Bytes("company_name")  # byteslice
    minted_indicator_key = Bytes("minted")  # uint64
    shared_indicator_key = Bytes("shared")  # uint64
    coins_key = Bytes("coins_id")  # uint64
    shares_key = Bytes("shares_id")  # uint64

    # operation
    op_mint_coins = Bytes("mint_coins")
    op_mint_shares = Bytes("mint_Shares")
    op_send_coins = Bytes("send_coins")

    # initialize company
    @Subroutine(TealType.none)
    def on_create():
        return Seq(
            App.globalPut(company_name_key, company_name),
            App.globalPut(minted_indicator_key, Int(0)),
            App.globalPut(shared_indicator_key, Int(0)),
            App.globalPut(coins_key, Int(0)),
            App.globalPut(shares_key, Int(0)),
        )

    # create assets (coins or shares)
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

    # one-time function create coins and reserve the coins
    @Subroutine(TealType.none)
    def mint_coins():
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(1),
            Assert(
                And(
                    # make sure the company has not created any crypto
                    App.globalGet(minted_indicator_key) == Int(0),
                    # operation, coins name, coins unit name, coins amount including decimal numbers, coins decimal, default frozen
                    Txn.application_args.length() == Int(6),
                )
            ),
            # mint coins
            create_tokens(Txn.application_args[1], Txn.application_args[2], Btoi(
                Txn.application_args[3]), Btoi(Txn.application_args[4]), Btoi(Txn.application_args[5]), Int(1)),
            # coins id
            App.globalPut(coins_key, (InnerTxn.created_asset_id())),
            # coins minted
            App.globalPut(minted_indicator_key, Int(1)),
            Approve(),
        )

    # one-time function create shares
    @Subroutine(TealType.none)
    def mint_shares():
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(1),
            Assert(
                And(
                    # make sure the company has not created shares
                    App.globalGet(shared_indicator_key) == Int(0),
                    # operation, company name, shares unit name, shares amount including decimal numbers, shares decimal, default frozen
                    Txn.application_args.length() == Int(6),
                )
            ),
            # mint shares
            create_tokens(Txn.application_args[1], Txn.application_args[2], Btoi(
                Txn.application_args[3]), Btoi(Txn.application_args[4]), Btoi(Txn.application_args[5]), Int(0)),
            # shares id
            App.globalPut(shares_key, InnerTxn.created_asset_id()),
            # shares minted
            App.globalPut(shared_indicator_key, Int(1)),
            Approve(),
        )

    # send assets
    @Subroutine(TealType.none)
    def send_tokens(asset_id, amount):
        return Seq(
            InnerTxnBuilder.Begin(),
            # create an asset that needs a reserve account
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: asset_id,
                    TxnField.asset_receiver: Txn.accounts[1],
                    TxnField.asset_amount: amount,
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    # check assets holding information
    @Subroutine(TealType.anytype)
    def check_assets_amount(asset_id):
        return Return(
            AssetHolding.balance(
                Txn.sender(), Txn.assets[0]).value()
            )

    # Send to reserve account
    @Subroutine(TealType.none)
    def send_coins():
        # to store coins id
        coins_id = ScratchVar(TealType.uint64)
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(1),
            # get asset ID of coins
            coins_id.store(App.globalGet(coins_key)),
            Assert(
                And(
                    # make sure the company has created coins
                    App.globalGet(minted_indicator_key) == Int(1),
                    # make sure the company own enough coins
                    check_assets_amount(
                        coins_id.load()) >= Btoi(Txn.application_args[1]),
                    # operation, amount of coins
                    Txn.application_args.length() == Int(2),
                )
            ),
            send_tokens(coins_id.load(), Txn.application_args[1]),
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
                    Txn.application_args[0] == op_send_coins,
                    send_coins(),
                ],
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('company_step_02.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application, version=5)
    f.write(compiled)

with open("company_step_02_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application, version=5)
    f.write(compiled)
