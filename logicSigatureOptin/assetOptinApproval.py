from pyteal import *


def approval():

    return Seq(
        Assert(
            And(
                Txn.type_enum() == TxnType.AssetTransfer,
                Txn.asset_receiver() == Txn.sender(),
                Txn.asset_amount() == Int(0),
            )
        ),
        Approve()
    )

with open('assetOptinApproval.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application, version=5)
    f.write(compiled)
