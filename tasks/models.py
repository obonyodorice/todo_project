from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
REVISION_BUFFER = 2           # finish revising this many days before the exam
CAT_MAX, EXAM_MAX = 30, 70    # average of the CATs is out of 30, main exam out of 70
GRADES = [(70, "A", "First Class"), (60, "B", "Second Upper"), (50, "C", "Second Lower"),
          (40, "D", "Pass"), (0, "E", "Fail")]


def grade_for(percent):
    p = int(percent + .5)
    return next((letter, label) for low, letter, label in GRADES if p >= low)


class Semester(models.Model):
    name = models.CharField(max_length=100)  # e.g. "Year 4 Sem 1"
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.start_date:%d %b %Y} to {self.end_date:%d %b %Y})"

    group = property(lambda self: str(self.start_date.year))


class Subject(models.Model):
    semester = models.ForeignKey(Semester, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-semester__start_date", "name"]

    def __str__(self):
        return f"{self.code} {self.name}".strip()

    @property
    def group(self):
        return self.semester.name if self.semester else "No semester"

    @property
    def next_exam(self):
        return self.exam_set.filter(date__gte=timezone.localdate()).first()

    @property
    def details(self):
        """Pulled live from the timetable, exams, revision and assignments, so it is always in sync."""
        out = [", ".join(f"{DAYS[c.day][:3]} {c.start:%H:%M}-{c.end:%H:%M}" for c in self.classsession_set.all())
               or "No classes in the timetable yet"]
        if self.next_exam:
            out.append(f"Next exam: {self.next_exam.title} on {self.next_exam.date:%a %d %b}")
        for count, label in ((self.revisiontopic_set.filter(done=False).count(), "topic(s) to revise"),
                             (self.assignment_set.filter(done=False).count(), "assignment(s) pending")):
            if count:
                out.append(f"{count} {label}")
        return out


class Assignment(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    done = models.BooleanField(default=False)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"{self.subject}: {self.title} (due {self.due_date})"

    group = property(lambda self: str(self.subject))
    headline = property(lambda self: self.title)
    details = property(lambda self: [f"Due {self.due_date:%a %d %b %Y}"])


class Exam(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)  # e.g. "CAT 1", "Main exam"
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.subject}: {self.title} ({self.date})"

    group = property(lambda self: str(self.subject))
    headline = property(lambda self: self.title)
    details = property(lambda self: [x for x in (f"{self.date:%a %d %b %Y}", f"{self.time:%H:%M}" if self.time else "", self.venue) if x])


class RevisionTopic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, null=True, blank=True, on_delete=models.SET_NULL,
                             help_text="Optional. Leave empty to use this unit's next exam.")
    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)

    class Meta:
        ordering = ["subject__name", "title"]

    def __str__(self):
        return f"{self.subject}: {self.title}"

    @property
    def exam_used(self):
        return self.exam or self.subject.next_exam

    @property
    def deadline(self):
        """Always the exam date minus the allowance, so it updates by itself if the exam moves."""
        return self.exam_used.date - timedelta(days=REVISION_BUFFER) if self.exam_used else None

    def sort_key(self):
        return self.deadline or timezone.localdate() + timedelta(days=9999)

    group = property(lambda self: str(self.subject))
    headline = property(lambda self: self.title)
    details = property(lambda self: [f"Finish by {self.deadline:%a %d %b} ({REVISION_BUFFER} days before {self.exam_used.title})"]
                       if self.exam_used else ["Deadline appears automatically once an exam is added for this unit"])


class ClassSession(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    day = models.IntegerField(choices=list(enumerate(DAYS)))
    start = models.TimeField()
    end = models.TimeField()
    kind = models.CharField(max_length=10, default="lecture",
                            choices=[("lecture", "Lecture"), ("lab", "Lab"), ("practical", "Practical")])
    venue = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["day", "start"]

    def __str__(self):
        return f"{self.get_day_display()} {self.start:%H:%M}-{self.end:%H:%M}: {self.subject} ({self.kind})"

    group = property(lambda self: self.get_day_display())
    headline = property(lambda self: f"{self.start:%H:%M}-{self.end:%H:%M} · {self.subject}")

    @property
    def details(self):
        topics = ", ".join(t.title for t in self.subject.revisiontopic_set.filter(done=False))
        exam = self.subject.next_exam
        out = [self.get_kind_display(), self.venue, f"To study: {topics}" if topics else "",
               f"Next exam: {exam.title} on {exam.date:%a %d %b}" if exam else ""]
        return [x for x in out if x]


class Result(models.Model):
    """One row per unit. Enter marks here; the Results page only ever shows grades."""
    subject = models.OneToOneField(Subject, on_delete=models.CASCADE)
    cat1 = models.FloatField("CAT 1", null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(CAT_MAX)],
                             help_text=f"Out of {CAT_MAX}. Leave empty if not done yet.")
    cat2 = models.FloatField("CAT 2", null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(CAT_MAX)],
                             help_text=f"Out of {CAT_MAX}. Leave empty if not done yet.")
    exam = models.FloatField("Main exam", null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(EXAM_MAX)],
                             help_text=f"Out of {EXAM_MAX}. Leave empty if not done yet.")

    class Meta:
        ordering = ["-subject__semester__start_date", "subject__name"]

    def __str__(self):
        return f"{self.subject} results"

    @property
    def cat(self):
        """CAT mark out of 30: the average of whichever CATs are done."""
        done = [c for c in (self.cat1, self.cat2) if c is not None]
        return sum(done) / len(done) if done else None

    @property
    def standing(self):
        """Percentage of the marks attempted so far."""
        earned = attempted = 0
        if self.cat is not None:
            earned, attempted = earned + self.cat, attempted + CAT_MAX
        if self.exam is not None:
            earned, attempted = earned + self.exam, attempted + EXAM_MAX
        return earned / attempted * 100 if attempted else None

    @property
    def final(self):
        return self.cat is not None and self.exam is not None

    @property
    def grade(self):
        return grade_for(self.standing) if self.standing is not None else None

    @property
    def advice(self):
        if not self.grade:
            return "Waiting for marks"
        return {"A": "On track", "B": "On track", "C": "Improve: start revising earlier",
                "D": "Needs attention", "E": "Retake or get help"}[self.grade[0]]


class Resource(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to="resources/", blank=True, help_text="PDF, Word or PowerPoint notes.",
                            validators=[FileExtensionValidator(["pdf", "doc", "docx", "ppt", "pptx"])])
    url = models.URLField(blank=True, help_text="Only for online links, e.g. YouTube. Not needed if you upload a file.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["subject__name", "title"]

    def __str__(self):
        return f"{self.subject}: {self.title}"

    def clean(self):
        if not self.file and not self.url:
            raise ValidationError("Upload a file or add a link.")

    link = property(lambda self: self.file.url if self.file else self.url)
    kind = property(lambda self: self.file.name.rsplit(".", 1)[-1].upper() if self.file else "LINK")  # PDF, DOCX, PPTX or LINK
    group = property(lambda self: str(self.subject))
    headline = property(lambda self: self.title)
    details = property(lambda self: [x for x in (self.notes, self.kind + " file" if self.file else "Link") if x])