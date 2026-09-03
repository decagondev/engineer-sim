"""Starter stub. Load the data and start exploring.

The interesting problem isn't plotting — it's deciding WHAT is worth surfacing
and dealing with the fact that usage (account_id) and billing (customer_id)
don't join without a mapping. Talk to Priya before you build.
"""
import pandas as pd


def load():
    usage = pd.read_csv("data/usage_export.csv")
    invoices = pd.read_csv("data/stripe_invoices.csv")
    return usage, invoices


if __name__ == "__main__":
    usage, invoices = load()
    print("usage rows:", len(usage), "| invoice rows:", len(invoices))
    # TODO: what would actually help Priya's team act sooner?
