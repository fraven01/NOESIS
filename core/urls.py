from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("work/", views.work, name="work"),
    path("personal/", views.personal, name="personal"),
    path("account/", views.account, name="account"),
    path("recording/<str:bereich>/", views.recording_page, name="recording_page"),
    path(
        "start-recording/<str:bereich>/",
        views.start_recording_view,
        name="start_recording",
    ),
    path(
        "stop-recording/<str:bereich>/",
        views.stop_recording_view,
        name="stop_recording",
    ),
    path(
        "toggle-recording/<str:bereich>/",
        views.toggle_recording_view,
        name="toggle_recording",
    ),
    path("upload/", views.upload_recording, name="upload_recording"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("upload-transcript/", views.upload_transcript, name="upload_transcript"),
    path(
        "personal/talkdiary/",
        views.talkdiary,
        {"bereich": "personal"},
        name="talkdiary_personal",
    ),
    path(
        "work/talkdiary/", views.talkdiary, {"bereich": "work"}, name="talkdiary_work"
    ),
    path("talkdiary/<int:pk>/", views.talkdiary_detail, name="talkdiary_detail"),
    path(
        "transcribe/<int:pk>/", views.transcribe_recording, name="transcribe_recording"
    ),
    path("recording/delete/<int:pk>/", views.recording_delete, name="recording_delete"),
    path("talkdiary-admin/", views.admin_talkdiary, name="admin_talkdiary"),
    path("projects-admin/", views.admin_projects, name="admin_projects"),
    path(
        "projects-admin/<int:pk>/delete/",
        views.admin_project_delete,
        name="admin_project_delete",
    ),
    path(
        "projects-admin/<int:pk>/cleanup/",
        views.admin_project_cleanup,
        name="admin_project_cleanup",
    ),
    path("projects-admin/prompts/", views.admin_prompts, name="admin_prompts"),
    path("projects-admin/models/", views.admin_models, name="admin_models"),
    path("projects-admin/anlage1/", views.admin_anlage1, name="admin_anlage1"),
    path(
        "projects-admin/anlage2/config/",
        views.anlage2_config,
        name="anlage2_config",
    ),
    path(
        "projects-admin/anlage2/",
        views.anlage2_function_list,
        name="anlage2_function_list",
    ),
    path(
        "projects-admin/anlage2/new/",
        views.anlage2_function_form,
        name="anlage2_function_new",
    ),
    path(
        "projects-admin/anlage2/<int:pk>/edit/",
        views.anlage2_function_form,
        name="anlage2_function_edit",
    ),
    path(
        "projects-admin/anlage2/<int:pk>/delete/",
        views.anlage2_function_delete,
        name="anlage2_function_delete",
    ),
    path(
        "projects-admin/anlage2/import/",
        views.anlage2_function_import,
        name="anlage2_function_import",
    ),
    path(
        "projects-admin/anlage2/export/",
        views.anlage2_function_export,
        name="anlage2_function_export",
    ),
    path(
        "projects-admin/anlage2/<int:function_pk>/subquestion/new/",
        views.anlage2_subquestion_form,
        name="anlage2_subquestion_new",
    ),
    path(
        "projects-admin/anlage2/subquestion/<int:pk>/edit/",
        views.anlage2_subquestion_form,
        name="anlage2_subquestion_edit",
    ),
    path(
        "projects-admin/anlage2/subquestion/<int:pk>/delete/",
        views.anlage2_subquestion_delete,
        name="anlage2_subquestion_delete",
    ),
    path("work/projekte/", views.projekt_list, name="projekt_list"),
    path("work/projekte/neu/", views.projekt_create, name="projekt_create"),
    path("work/projekte/<int:pk>/", views.projekt_detail, name="projekt_detail"),
    path("work/projekte/<int:pk>/bearbeiten/", views.projekt_edit, name="projekt_edit"),
    path(
        "work/projekte/<int:pk>/anlage/",
        views.projekt_file_upload,
        name="projekt_file_upload",
    ),
    path("work/projekte/<int:pk>/check/", views.projekt_check, name="projekt_check"),
    path(
        "work/projekte/<int:pk>/status/",
        views.projekt_status_update,
        name="projekt_status_update",
    ),
    path(
        "work/projekte/<int:pk>/functions-check/",
        views.projekt_functions_check,
        name="projekt_functions_check",
    ),
    path(
        "work/anlage/<int:pk>/verify-feature/",
        views.anlage2_feature_verify,
        name="anlage2_feature_verify",
    ),
    path(
        "ajax/task-status/<str:task_id>/",
        views.ajax_check_task_status,
        name="ajax_check_task_status",
    ),
    path(
        "ajax/save-review-item/",
        views.ajax_save_anlage2_review_item,
        name="ajax_save_review_item",
    ),
    path(
        "work/projekte/<int:pk>/anlage/<int:nr>/check/",
        views.projekt_file_check,
        name="projekt_file_check",
    ),
    path(
        "work/anlage/<int:pk>/check/",
        views.projekt_file_check_pk,
        name="projekt_file_check_pk",
    ),
    path(
        "work/anlage/<int:pk>/check-view/",
        views.projekt_file_check_view,
        name="projekt_file_check_view",
    ),
    path(
        "work/anlage/<int:pk>/edit-json/",
        views.projekt_file_edit_json,
        name="projekt_file_edit_json",
    ),
    path(
        "work/anlage/<int:pk>/email/",
        views.anlage1_generate_email,
        name="anlage1_generate_email",
    ),
    path(
        "work/projekte/<int:pk>/gap-analysis/",
        views.projekt_gap_analysis,
        name="projekt_gap_analysis",
    ),
    path(
        "work/projekte/<int:pk>/summary/",
        views.projekt_management_summary,
        name="projekt_management_summary",
    ),
    path(
        "work/projekte/<int:pk>/gutachten/",
        views.projekt_gutachten,
        name="projekt_gutachten",
    ),
    path(
        "work/projekte/<int:pk>/gutachten/view/",
        views.gutachten_view,
        name="gutachten_view",
    ),
    path(
        "work/projekte/<int:pk>/gutachten/edit/",
        views.gutachten_edit,
        name="gutachten_edit",
    ),
    path(
        "work/projekte/<int:pk>/gutachten/delete/",
        views.gutachten_delete,
        name="gutachten_delete",
    ),
    path(
        "work/projekte/<int:pk>/gutachten/llm-check/",
        views.gutachten_llm_check,
        name="gutachten_llm_check",
    ),
    path("projects/<int:pk>/", views.project_detail_api, name="project_detail_api"),
    path(
        "projects/<int:pk>/llm-check/",
        views.project_llm_check,
        name="project_llm_check",
    ),
    path(
        "login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
