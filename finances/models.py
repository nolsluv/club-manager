from django.db import models
from django.db.models import Sum, Q
from members.models import Club, Member


class FinancialAccount(models.Model):
    class Type(models.TextChoices):
        CHECKING = "checking", "Checking"
        SAVINGS = "savings", "Savings"
        CASH = "cash", "Cash box"
        OTHER = "other", "Other"

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="finance_accounts")
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=Type.choices, default=Type.CHECKING)
    institution = models.CharField(max_length=100, blank=True)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)  # "prior" accounts = inactive
    created_at = models.DateTimeField(auto_now_add=True)

    def balance(self):
        agg = self.entries.aggregate(
            inc=Sum("amount", filter=~Q(kind="expense")),
            exp=Sum("amount", filter=Q(kind="expense")),
        )
        return self.opening_balance + (agg["inc"] or 0) - (agg["exp"] or 0)

    def __str__(self):
        return f"{self.name} ({self.club.name})"


class FinanceEntry(models.Model):
    class Kind(models.TextChoices):
        FUNDRAISER = "fundraiser", "Fundraiser"
        MONTHLY = "monthly", "Monthly payment (dues)"
        OTHER_INCOME = "other", "Other income"
        EXPENSE = "expense", "Expense"

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="finance_entries")
    account = models.ForeignKey(FinancialAccount, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="entries")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # always positive
    date = models.DateField()
    created_by = models.ForeignKey(Member, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]

    @property
    def is_expense(self):
        return self.kind == self.Kind.EXPENSE