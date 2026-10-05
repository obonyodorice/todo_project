from django.urls import path

from . import views as v
from .models import Assignment, ClassSession, Exam, Resource, Result, RevisionTopic, Semester, Subject

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("result/", v.results, name="result_list"),
    path("result/<int:pk>/edit/", v.Update.as_view(model=Result, fields=["cat1", "cat2", "exam"]), name="result_edit"),
    path("resource/", v.resources, name="resource_list"),
]

for m in (Assignment, Exam, RevisionTopic, ClassSession, Resource, Subject, Semester):
    n = m._meta.model_name
    if m is not Resource:  # the resources page is its own table (views.resources)
        urlpatterns.append(path(f"{n}/", v.List.as_view(model=m), name=f"{n}_list"))
    urlpatterns += [
        path(f"{n}/add/", v.Create.as_view(model=m), name=f"{n}_add"),
        path(f"{n}/<int:pk>/edit/", v.Update.as_view(model=m), name=f"{n}_edit"),
        path(f"{n}/<int:pk>/remove/", v.Delete.as_view(model=m), name=f"{n}_remove"),
    ]
    if hasattr(m, "done"):  # only assignments and topics can be marked done
        urlpatterns.append(path(f"{n}/<int:pk>/toggle/", v.toggle, {"model": m}, name=f"{n}_toggle"))