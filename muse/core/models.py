from django.db import models

# Create your models here.
class Payload(models.Model):
    repo = models.CharField(max_length=255)
    payload = models.TextField()
    build_id = models.CharField(max_length=30)
    branch = models.CharField(max_length=255)

    class Meta:
        unique_together = ('repo', 'build_id')

    def __unicode__(self):
	return '(%d, %s)' % (self.id, self.repo)


class Badge(models.Model):
    repo = models.CharField(max_length=255)
    branch = models.CharField(max_length=255)
    status = models.CharField(max_length=30, default='SUCCESS')

    class Meta:
        unique_together = ('repo', 'branch', 'status')

    def __unicode__(self):
        return '(%s, %s)' % (self. repo, self.status)
