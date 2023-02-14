import sys
sys.path.insert(0, '..')
from pyteal.ast.bytes import Bytes
from pyteal import *
from pyteal_helpers import program

def approval():

    # box key information
    activated_by_voting = Bytes("activated") # uint64
    status_key = Bytes("voting_status") # uint64

    # governor key infromation
    voting_end_key = Bytes("voting_end")  # uint64
    proposal_key = Bytes("proposal")  # byteslice

    # operation
    get_result_string = Bytes("update_result")

    # expression
    pending = Bytes("pending...")

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

    # initialize voting contract
    @Subroutine(TealType.none)
    def on_create():
        return Seq(
            Assert(
                And(
                    # proposal
                    Txn.application_args.length() == Int(1),
                ),
            ),
            App.globalPut(activated_by_voting, Int(0)),
            App.globalPut(Txn.application_args[0], pending),
        )

    # get result from voting
    @Subroutine(TealType.none)
    def get_result():
        voting_ends = ScratchVar(TealType.uint64)
        proposal = ScratchVar(TealType.bytes)
        return Seq(
            voting_ends.store(get_global_value(Txn.sender(), voting_end_key)),
            proposal.store(get_global_value(Txn.sender(), proposal_key)),
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            Assert(
                And(
                    # make sure this box has not been occupied
                    App.globalGet(activated_by_voting) == Int(0),
                    # make sure the voting has ended
                    voting_ends.load() > Global.latest_timestamp(),
                    # make sure the proposal is same as the voting governor and the result has not been revealed
                    App.globalGet(proposal.load()) == pending,
                    # operation, voting status, voting result
                    Txn.application_args.length() == Int(3)
                ),
            ),
            # 
            App.globalPut(activated_by_voting, Int(1)),
            App.globalPut(status_key, Txn.application_args[1]),
            App.globalPut(proposal.load(), Txn.application_args[2]),
            Approve(),
        )

    return program.event(
        init=Seq(
            on_create(),
            Approve(),
        ),
        no_op=Seq(
            Cond(
                [Txn.application_args[0] == get_result_string,
                get_result(),]
            ),
            Reject(),
        ),
    )

def clear():
    return Approve()


with open('box.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)

with open("box_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)

