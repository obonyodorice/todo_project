from django import forms
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import DAYS, Assignment, ClassSession, Exam, Result, Subject, grade_for


def tile(icon, label, count, url, note, state="", progress=None):
    return locals()


def in_days(d):
    n = (d - timezone.localdate()).days
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


def dashboard(request):
    today, now = timezone.localdate(), timezone.localtime().time()
    classes = list(ClassSession.objects.filter(day=today.weekday()))
    coming = [c for c in classes if c.start >= now]
    pending = list(Assignment.objects.filter(done=False))
    overdue = [a for a in pending if a.due_date < today]
    exams = list(Exam.objects.filter(date__gte=today))
    left = lambda model: round(100 * (1 - len(pending) / model.objects.count())) if model.objects.count() else None

    tiles = [
        tile("calendar", "Classes today", len(classes), reverse("classsession_list") + f"?open={DAYS[today.weekday()]}",
             f"Next: {coming[0].start:%H:%M} {coming[0].subject.name}" if coming else "All done for today" if classes else "No classes, free day"),
        tile("clock", "Upcoming exams", len(exams), reverse("exam_list") + "?open=all",
             f"Next: {exams[0].title} {in_days(exams[0].date)}" if exams else "None scheduled",
             "alert" if exams and (exams[0].date - today).days <= 3 else ""),
        tile("file", "Assignments pending", len(pending), reverse("assignment_list") + "?pending=1&open=all",
             f"{len(overdue)} overdue!" if overdue else f"Next due {in_days(pending[0].due_date)}" if pending else "All caught up",
             "alert" if overdue else "ok" if not pending else "", left(Assignment)),
    ]
    units = [u for u in Subject.objects.prefetch_related("resource_set") if u.resource_set.all()]
    return render(request, "./dashboard.html", {"tiles": tiles, "units": units})


def resources(request):
    units = Subject.objects.select_related("semester").prefetch_related("resource_set")
    return render(request, "./resources.html", {"units": units})


class Redirect:
    """After saving or deleting, go back to that model's list page."""
    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}_list")


class Form(Redirect):
    fields = "__all__"
    template_name = "./form.html"

    def get_initial(self):
        return self.request.GET.dict()  # lets a link like ?subject=3 pre-fill the form

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for f in form.fields.values():  # use the browser's date/time pickers
            if isinstance(f, forms.DateField):
                f.widget.input_type = "date"
            elif isinstance(f, forms.TimeField):
                f.widget.input_type = "time"
        return form


class Create(Form, CreateView):
    pass


class Update(Form, UpdateView):
    pass


class Delete(Redirect, DeleteView):
    template_name = "./confirm_delete.html"


class List(ListView):
    template_name = "./list.html"

    def get_queryset(self):
        items = super().get_queryset()
        sort_key = getattr(self.model, "sort_key", None)  # revision topics sort by their live deadline
        return sorted(items, key=sort_key) if sort_key else items

    def get_context_data(self, **kwargs):
        meta = self.model._meta
        ctx = super().get_context_data(name=meta.model_name, title=meta.verbose_name_plural, **kwargs)
        if hasattr(self.model, "group"):  # collapsible sections: by day, subject or semester
            groups = {}
            for obj in ctx["object_list"]:
                groups.setdefault(obj.group, []).append(obj)
            ctx["groups"] = list(groups.items())
        return ctx


def results(request):
    for subject in Subject.objects.all():  # every unit gets a results row automatically
        Result.objects.get_or_create(subject=subject)
    by_semester = {}
    for r in Result.objects.select_related("subject__semester"):
        by_semester.setdefault(r.subject.semester or "No semester", []).append(r)
    rows = []
    for semester, rs in by_semester.items():
        graded = [r for r in rs if r.grade]
        rows.append({
            "semester": semester, "results": rs, "done": sum(r.final for r in rs),
            "average": grade_for(sum(r.standing for r in graded) / len(graded)) if graded else None,
            "adjust": [r for r in graded if r.grade[0] in "CDE"],
        })
    return render(request, "./results.html", {"rows": rows})


@require_POST
def toggle(request, pk, model):
    obj = get_object_or_404(model, pk=pk)
    obj.done = not obj.done
    obj.save()
    return redirect(f"{model._meta.model_name}_list")