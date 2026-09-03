"""Stub signup backend. Sends a verification email on submit."""

def signup(email, password):
    # TODO: talk to Maya about what actually goes wrong for new users
    send_verification_email(email)


def send_verification_email(email):
    pass  # slow? spam? worth investigating
