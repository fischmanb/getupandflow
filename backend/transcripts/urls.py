from django.urls import path

from .views import TranscriptFeedView, TranscriptPollView, ZoomWebhookView

urlpatterns = [
    path("zoom/webhook/", ZoomWebhookView.as_view(), name="zoom-webhook"),
    path("transcripts/feed/", TranscriptFeedView.as_view(), name="transcript-feed"),
    path("transcripts/poll/", TranscriptPollView.as_view(), name="transcript-poll"),
]
