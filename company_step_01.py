from pyteal import *
from pyteal.ast.bytes import Bytes
from pyteal_helpers import program


def approval():

    # company name
    company = Bytes("Test01")

    # company key information
    public_company_name = Bytes("company_name")  # byteslice
    public_minted = Bytes("minted")  # uint64
    public_shared = Bytes("shared")  # uint64
    public_crypto = Bytes("crypto_id")  # byteslice
    public_crypto_base = Bytes("crypto_base")  # uint64
    public_shares = Bytes("shares_id")  # byteslice

    # operation
    op_mint_crypto = Bytes("crypto")
    op_mint_share = Bytes("share")

    # initial company
    @Subroutine(TealType.none)
    def on_create():
        return Seq(
            App.globalPut(public_company_name, company),
            App.globalPut(public_minted, Int(0)),
            App.globalPut(public_shared, Int(0)),
            App.globalPut(public_crypto, Int(0)),
            App.globalPut(public_crypto_base, Int(0)),
            App.globalPut(public_shares, Int(0)),
        )

    # create assets (crypto or shares)
    @Subroutine(TealType.none)
    def create_tokens():
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: Txn.application_args[1],
                    TxnField.config_asset_unit_name: Txn.application_args[2],
                    TxnField.config_asset_total: Btoi(Txn.application_args[3]),
                    TxnField.config_asset_decimals: Btoi(Txn.application_args[4]),
                    TxnField.config_asset_default_frozen: Btoi(Txn.application_args[5]),
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    # one-time function create crypto
    @Subroutine(TealType.none)
    def mint_crypto():
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
                    App.globalGet(public_minted) == Int(0),
                    # operation, crypto name, crypto unit name, crypto amount including decimal numbers, crypto decimal, default frozen, crypto amount in integer
                    Txn.application_args.length() == Int(7),
                )
            ),
            # mint crypto
            create_tokens(),
            # crypto id
            App.globalPut(public_crypto, (InnerTxn.created_asset_id())),
            # crypto amount in vault
            App.globalPut(public_crypto_base, Btoi(Txn.application_args[6])),
            # crypto minted
            App.globalPut(public_minted, Int(1)),
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
                    App.globalGet(public_shared) == Int(0),
                    # operation, company name, shares unit name, shares amount including decimal numbers, shares decimal, default frozen
                    Txn.application_args.length() == Int(6),
                )
            ),
            # mint shares
            create_tokens(),
            # shares id
            App.globalPut(public_shares, InnerTxn.created_asset_id()),
            # shares minted
            App.globalPut(public_shared, Int(1)),
            Approve(),
        )

    return program.event(
        init=Seq (
            on_create(),
            Approve(),
        ),
        no_op=Seq(
            Cond(
                [
                    Txn.application_args[0] == op_mint_crypto,
                    mint_crypto(),
                ],
                [
                    Txn.application_args[0] == op_mint_share,
                    mint_shares(),
                ],
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('company_step_01.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application, version=5)
    f.write(compiled)

with open("company_step_01_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application, version=5)
    f.write(compiled)
