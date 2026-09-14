"""Naive answer stub. No grounding, no citation, no evaluation.

The interesting problem isn't wiring up an LLM — it's that the three docs in
../docs disagree about fees, nothing ties an answer to an approved source, and
there's no way to know if an answer is right before customers see it. Talk to Dev
(and Compliance) about what "good" has to mean here.
"""


def answer(question: str) -> str:
    # TODO: ground answers in an approved source and cite it.
    # TODO: how would you measure answer quality BEFORE launch?
    return "I think instant transfers cost 1% — but I'm not sure."


if __name__ == "__main__":
    print(answer("How much is an instant transfer?"))
