import sys
sys.path.insert(0, '..')
from pyteal.ast.bytes import Bytes
from pyteal import *
from pyteal_helpers import program

def approval():

    return Seq(
        program.check_self(
                group_size=Int(2),
                group_index=Int(1),
            ),
        Assert(
            And(
                Gtxn[0].sender() == Addr("P2UWZURRK3UGAUFY5RFFX7AXFFEU5576KZKGM5U5FPRPIE6Y5CNMPAIL4E"),
                Txn.type_enum() == TxnType.AssetTransfer,
                Txn.asset_receiver() == Txn.sender(),
                Txn.asset_amount() == Int(0),
            )
        ),
        Approve()
    )

with open('assetOptinApprovalUpdated.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application, version=5)
    f.write(compiled)
