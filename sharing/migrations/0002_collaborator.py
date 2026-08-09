from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sharing', '0001_initial'),
        ('storage', '0001_initial'),
        migrations.swappable_dependency('accounts.CustomUser'),
    ]

    operations = [
        migrations.CreateModel(
            name='Collaborator',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission', models.CharField(choices=[('view', 'View'), ('edit', 'Edit'), ('delete', 'Delete')], default='view', max_length=20)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('file_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='collaborators', to='storage.fileitem')),
                ('folder', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='collaborators', to='storage.folder')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collaborations', to='accounts.customuser')),
            ],
            options={
                'unique_together': {('user', 'file_item', 'folder')},
            },
        ),
    ]