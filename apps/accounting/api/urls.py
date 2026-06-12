from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounting.api.views import (
    AccountViewSet,
    AccountingPeriodViewSet,
    AuditLogViewSet,
    BillSubmissionView,
    EntityViewSet,
    CreditSubmissionView,
    JournalEntryViewSet,
    InvoiceSubmissionView,
    PaymentSubmissionView,
    ReportViewSet,
    RefundSubmissionView,
    TaxCodeViewSet,
)

router = DefaultRouter()
router.register("entities", EntityViewSet, basename="entity")
router.register("accounts", AccountViewSet, basename="account")
router.register("periods", AccountingPeriodViewSet, basename="period")
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("reports", ReportViewSet, basename="report")
router.register("tax-codes", TaxCodeViewSet, basename="tax-code")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("invoices/", InvoiceSubmissionView.as_view(), name="api-invoice-submission"),
    path("bills/", BillSubmissionView.as_view(), name="api-bill-submission"),
    path("payments/", PaymentSubmissionView.as_view(), name="api-payment-submission"),
    path("credits/", CreditSubmissionView.as_view(), name="api-credit-submission"),
    path("refunds/", RefundSubmissionView.as_view(), name="api-refund-submission"),
    path("", include(router.urls)),
]
