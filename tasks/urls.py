from django.urls import path

from . import views as v
from .models import Assignment, ClassSession, Exam, Resource, Result, RevisionTopic, Semester, Subject

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("result/", v.results, name="result_list"),
    path("result/<int:pk>/edit/", v.Update.as_view(model=Result, fields=["cat1", "cat2", "exam"]), name="result_edit"),
]

for m in (Assignment, Exam, RevisionTopic, ClassSession, Resource, Subject, Semester):
    n = m._meta.model_name
    urlpatterns += [
        path(f"{n}/", v.List.as_view(model=m), name=f"{n}_list"),
        path(f"{n}/add/", v.Create.as_view(model=m), name=f"{n}_add"),
        path(f"{n}/<int:pk>/edit/", v.Update.as_view(model=m), name=f"{n}_edit"),
        path(f"{n}/<int:pk>/delete/", v.Delete.as_view(model=m), name=f"{n}_delete"),
    ]
    if hasattr(m, "done"):  # only assignments and topics can be marked done
        urlpatterns.append(path(f"{n}/<int:pk>/toggle/", v.toggle, {"model": m}, name=f"{n}_toggle"))