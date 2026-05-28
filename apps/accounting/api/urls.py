from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounting.api.views import AccountViewSet, AccountingPeriodViewSet, AuditLogViewSet, EntityViewSet, JournalEntryViewSet

router = DefaultRouter()
router.register("entities", EntityViewSet, basename="entity")
router.register("accounts", AccountViewSet, basename="account")
router.register("periods", AccountingPeriodViewSet, basename="period")
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [path("", include(router.urls))]
