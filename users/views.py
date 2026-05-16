from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from .forms import VendorRegisterForm, VendorProfileForm
from .models import VendorProfile
from django.contrib.auth.decorators import login_required

def register_view(request):
    if request.method == "POST":
        form = VendorRegisterForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data["institution_email"]
            password = form.cleaned_data["password"]

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=form.cleaned_data["full_name"]
            )

            VendorProfile.objects.create(
                user=user,
                full_name=form.cleaned_data["full_name"],
                whatsapp_number=form.cleaned_data["whatsapp_number"],
                institution_email=email,
                company_name=form.cleaned_data["company_name"],
                business_field=form.cleaned_data["business_field"],
                location_type=form.cleaned_data["location_type"],
                province=form.cleaned_data.get("province"),
                city_or_regency=form.cleaned_data.get("city_or_regency"),
                country=form.cleaned_data.get("country"),
            )

            login(request, user)
            return redirect("dashboard")

    else:
        form = VendorRegisterForm()

    return render(request, "users/register.html", {"form": form})


@login_required
def profile_view(request):
    profile, created = VendorProfile.objects.get_or_create(
        user=request.user,
        defaults={
            "full_name": request.user.get_full_name() or request.user.username,
            "institution_email": request.user.email or request.user.username,
            "company_name": "",
            "whatsapp_number": "",
            "business_field": "",
        }
    )

    if request.method == "POST":
        form = VendorProfileForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()
            return redirect("vendor_profile")
    else:
        form = VendorProfileForm(instance=profile)

    return render(request, "users/profile.html", {
        "form": form,
        "profile": profile,
        "created": created,
    })