"""Current bill settlement balances, scoped to the originating integration client.

Payment applications include cash/card settlements and vendor credits. General
journals without bill applications cannot be attributed to an individual bill.
"""
from decimal import Decimal

from apps.accounting.models import Bill, JournalEntry


def bill_payment_statuses(*, entity, client_id, references):
    bills = Bill.objects.filter(
        entity=entity, external_source_client_id=client_id,
        external_bill_number__in=references,
    ).prefetch_related("payment_applications__payment", "payment_applications__journal_entry")
    results = []
    for bill in bills:
        paid = Decimal("0.00")
        credited = Decimal("0.00")
        review = False
        for application in bill.payment_applications.all():
            if application.journal_entry_id and application.journal_entry.status != JournalEntry.Status.POSTED:
                review = True
            if application.payment.is_credit_adjustment:
                credited += application.applied_amount
            else:
                paid += application.applied_amount
        balance = bill.total_amount - paid - credited
        if bill.status == Bill.Status.VOIDED:
            payment_status = "voided"
        elif bill.status == Bill.Status.DRAFT:
            payment_status = "not_posted"
        elif review or balance < 0:
            payment_status = "needs_review"
        elif balance == 0:
            payment_status = "paid"
        elif paid + credited > 0:
            payment_status = "partially_paid"
        else:
            payment_status = "unpaid"
        results.append({
            "id": bill.pk, "external_bill_number": bill.external_bill_number,
            "status": bill.status, "payment_status": payment_status,
            "total_amount": str(bill.total_amount), "amount_paid": str(paid),
            "amount_credited": str(credited), "outstanding_balance": str(balance),
        })
    return results
