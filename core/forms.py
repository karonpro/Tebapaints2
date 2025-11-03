from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from .models import UserProfile, Location  # Import models, don't define them here

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, initial='staff')
    
    assigned_location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True),
        required=False,
        empty_label="Select Location (Optional for Admin)"
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'assigned_location')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_location'].queryset = Location.objects.filter(is_active=True)
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            # Create or update user profile
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.assigned_location = self.cleaned_data['assigned_location']
            profile.save()
        
        return user

class CustomUserChangeForm(UserChangeForm):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    
    assigned_location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True),
        required=False,
        empty_label="Select Location (Optional for Admin)"
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'role', 'assigned_location')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Remove password field
        self.fields.pop('password', None)
        
        # Set initial values from profile
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['role'].initial = self.instance.profile.role
            self.fields['assigned_location'].initial = self.instance.profile.assigned_location
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if commit:
            # Update user profile
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.assigned_location = self.cleaned_data['assigned_location']
            profile.save()
        
        return user

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('role', 'assigned_location')
        widgets = {
            'role': forms.Select(attrs={'class': 'form-control'}),
            'assigned_location': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_location'].queryset = Location.objects.filter(is_active=True)
        self.fields['assigned_location'].required = False

# ADD THIS FORM FOR LOCATION MANAGEMENT
class LocationForm(forms.ModelForm):
    class Meta:
        model = Location  # This references the Location model from models.py
        fields = ['name', 'address', 'phone', 'email', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }