from django.db import models


class IndexedDocument(models.Model):
    document_path = models.CharField(max_length=512, unique=True)
    source_name = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64)
    embedding_model = models.CharField(max_length=128)
    chunk_size = models.PositiveIntegerField()
    chunk_overlap = models.PositiveIntegerField()
    chunk_profile = models.CharField(max_length=255)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["embedding_model", "chunk_size", "chunk_overlap"]),
        ]

    def __str__(self):
        return f"{self.source_name} ({self.content_hash[:8]})"
