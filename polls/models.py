from django.db import models
from django.db.models import Count
from django.utils import timezone

from members.models import Club, Member, Notification


class Poll(models.Model):
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="polls")
    created_by = models.ForeignKey(
        Member, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_polls"
    )
    question = models.CharField(max_length=200)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    # the inbox notification that announced this poll
    notification = models.OneToOneField(
        Notification, null=True, blank=True, on_delete=models.SET_NULL, related_name="poll"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.question

    @property
    def is_open(self):
        return timezone.now() < self.expires_at

    def results(self):
        """Return (options, total_votes). Each option gets vote_count, percent, is_leading."""
        options = list(self.options.annotate(vote_count=Count("votes")))
        total = sum(o.vote_count for o in options)
        top = max((o.vote_count for o in options), default=0)
        for o in options:
            o.percent = round(o.vote_count / total * 100) if total else 0
            o.is_leading = total > 0 and o.vote_count == top
        return options, total


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=100)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Vote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="poll_votes")
    voted_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # one vote per member per poll; changing a vote updates this row
            models.UniqueConstraint(fields=["poll", "member"], name="one_vote_per_member_per_poll")
        ]

    def __str__(self):
        return f"{self.member} -> {self.option}"