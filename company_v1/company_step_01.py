from pyteal import *
from pyteal.ast.bytes import Bytes
import sys
sys.path.insert(0, '..')
from pyteal_helpers import program


def approval():

    # company key information
    company_name_key = Bytes("company_name")  # byteslice
    minted_indicator_key = Bytes("minted")  # uint64
    shared_indicator_key = Bytes("shared")  # uint64
    coins_key = Bytes("coins_id")  # uint64
    shares_key = Bytes("shares_id")  # uint64
    founder_key = Bytes("founder")  # byteslice
    number_of_founders_key = Bytes("number_of_founder") # uint64

    # operation
    op_mint_coins = Bytes("mint_coins")
    op_mint_shares = Bytes("mint_shares")

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
        return Seq(
            Assert(
                Txn.application_args.length() == Int(1)
            ),  
            App.globalPut(company_name_key, Txn.application_args[0]),
            App.globalPut(minted_indicator_key, Int(0)),
            App.globalPut(shared_indicator_key, Int(0)),
            App.globalPut(coins_key, Int(0)),
            App.globalPut(shares_key, Int(0)),
            For(i.store(Int(1)), i.load() < (Txn.accounts.length() + Int(1)), i.store(i.load() + Int(1))).Do(
                App.globalPut(Concat(founder_key, convert_uint_to_bytes(i.load())),
                              Txn.accounts[(i.load())])
            ),
            App.globalPut(number_of_founders_key, (i.load() - Int(1))),
        )

    # create assets (coins or shares)
    @Subroutine(TealType.none)
    def create_tokens(asset_name, asset_unit_name, asset_total, asset_decimal, asset_default_frozen, asset_reserve):
        return Seq(
            InnerTxnBuilder.Begin(),
            If(asset_reserve == Int(1))
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
            program.check_rekey_zero(Int(1)),
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
            program.check_rekey_zero(Int(1)),
            Assert(
                And(
                    # make sure the company has not created shares
                    App.globalGet(shared_indicator_key) == Int(0),
                    # shares name equals to company name
                    Txn.application_args[1] == App.globalGet(company_name_key),
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
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('company_step_01.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application, version=MAX_PROGRAM_VERSION)
    f.write(compiled)

with open("company_step_01_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application, version=MAX_PROGRAM_VERSION)
    f.write(compiled)
