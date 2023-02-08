import sys
sys.path.insert(0, '..')
from pyteal_helpers import program
from pyteal import *
from pyteal.ast.bytes import Bytes


def approval():

    # governor key information
    governorToken_key = Bytes("governor_token")  # byteslice
    min_token_amount_key = Bytes("min_token_to_vote")  # uint64
    required_number_of_choices_key = Bytes("choose")  # uint64
    proposal_key = Bytes("proposal") # byteslice
    # voting_start_key = Bytes("voting_start") # uint64
    voting_end_key = Bytes("voting_end")  # uint64
    voting_delay_key = Bytes("voting_delay")  # uint64
    option_key = Bytes("option")  # uint64
    total_number_of_options_key = Bytes("total_number_of_options")  # uint64
    voted_key = Bytes("voted")  # uint64
    # number_of_votes_key = Bytes("number_of_votes") # uint64

    # operation
    vote = Bytes("vote")
    # Exp
    # sender = Bytes("sender")
    # receiver = Bytes("receiver")

    # @Subroutine(TealType.bytes)
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

    # initialize voting contract
    @Subroutine(TealType.none)
    def on_create():
        time_now = ScratchVar(TealType.uint64)
        i = ScratchVar(TealType.uint64)
        option_number = ScratchVar(TealType.uint64)
        return Seq(
            time_now.store(Global.latest_timestamp()),
            option_number.store(Int(0)),
            Assert(
                And(
                    Txn.application_args.length() >= Int(6),
                )
            ),
            App.globalPut(governorToken_key, Txn.assets[0]),
            App.globalPut(proposal_key, Txn.application_args[0]),
            App.globalPut(min_token_amount_key, Btoi(Txn.application_args[1])),
            App.globalPut(required_number_of_choices_key,
                          Btoi(Txn.application_args[2])),
            App.globalPut(voting_end_key, Btoi(
                Txn.application_args[3]) + time_now.load()),
            App.globalPut(voting_delay_key, Btoi(Txn.application_args[4])),
            For(i.store(Int(5)), i.load() < (Txn.application_args.length()), i.store(i.load() + Int(1))).Do(
                option_number.store(option_number.load() + Int(1)),
                App.globalPut(Concat(option_key, convert_uint_to_bytes(
                    option_number.load()), Bytes(": "), Txn.application_args[i.load()]), Int(0)),
            ),
            App.globalPut(total_number_of_options_key, option_number.load()),
        )


    # optIn to initialize the voted value
    @Subroutine(TealType.none)
    def optIn_to_vote(account: Expr):
        return Seq(
            App.localPut(account, voted_key, Int(0)),
        )

    # vote from candidates
    @Subroutine(TealType.none)
    def voting():
        governorToken = ScratchVar(TealType.uint64)
        required_number_of_token = ScratchVar(TealType.uint64)
        required_number_of_choices = ScratchVar(TealType.uint64)
        i = ScratchVar(TealType.uint64)
        accountAssetBalance = AssetHolding.balance(Txn.sender(), Txn.assets[0])
        return Seq(
            # basic sanity checks
            program.check_self(
                group_size=Int(1),
                group_index=Int(0),
            ),
            program.check_rekey_zero(Int(1)),
            governorToken.store(App.globalGet(governorToken_key)),
            required_number_of_token.store(
                App.globalGet(min_token_amount_key)),
            required_number_of_choices.store(
                App.globalGet(required_number_of_choices_key)),
            accountAssetBalance,
            Assert(
                And(
                    # make sure the candidate has optedIn
                    App.optedIn(Txn.sender(), Int(0)),
                    # make sure the foreign asset is the governor token
                    Txn.assets[0] == governorToken.load(),
                    # make sure the candidate holds enough tokens to vote
                    accountAssetBalance.value() >= required_number_of_token.load(),
                    # make sure the candidate can only vote once
                    App.localGet(Txn.sender(), voted_key) == Int(0),
                    # operation, option1, ..., optionX
                    Txn.application_args.length() == required_number_of_choices.load() + Int(1),
                )
            ),
            # make sure options in arguments are correct and selectable
            For(i.store(Int(1)), i.load() <= required_number_of_choices.load(), i.store(i.load() + Int(1))).Do(
                Assert(
                    App.globalGet(
                        Txn.application_args[i.load()]) >= Int(0),
                )
            ),
            # update voted options
            For(i.store(Int(1)), i.load() <= required_number_of_choices.load(), i.store(i.load() + Int(1))).Do(
                App.globalPut(Txn.application_args[i.load()], App.globalGet(
                    Txn.application_args[i.load()]) + Int(1)),
            ),
            # update voted candidates
            App.localPut(Txn.sender(), voted_key, Int(1)),
            Approve(),
        )

    return program.event(
        init=Seq(
            on_create(),
            Approve(),
        ),
        opt_in=Seq(
            optIn_to_vote(Int(0)),
            Approve(),
        ),
        no_op=Seq(
            Cond(
                [Txn.application_args[0] == vote,
                 voting(),]
            ),
            Reject(),
        ),
    )


def clear():
    return Approve()


with open('governor.teal', 'w') as f:
    compiled = compileTeal(approval(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)

with open("governor_clear.teal", "w") as f:
    compiled = compileTeal(clear(), Mode.Application,
                           version=MAX_PROGRAM_VERSION)
    f.write(compiled)
