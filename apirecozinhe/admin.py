from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apirecozinhe.models import *


@admin.register(User)
class ReCozinheUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('ReCozinhe', {'fields': ('avatar', 'monthly_goal_kg')}),)


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'source', 'prep_time_minutes', 'difficulty']
    list_filter = ['source', 'category', 'difficulty']
    search_fields = ['title']
    filter_horizontal = ['key_ingredients']
    inlines = [RecipeIngredientInline]


class ReuseTipInline(admin.TabularInline):
    model = ReuseTip
    extra = 0


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'identified_ingredient', 'confidence', 'timestamp_create']
    list_filter = ['status', 'source']
    inlines = [ReuseTipInline]


@admin.register(Reuse)
class ReuseAdmin(admin.ModelAdmin):
    list_display = ['user', 'recipe', 'tip', 'saved_kg', 'reused_at']


admin.site.register(Category)
admin.site.register(Ingredient)
