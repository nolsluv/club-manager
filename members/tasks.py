from django.core.mail import EmailMultiAlternatives


def send_password_reset_email(subject, text_body, html_body, from_email, to_email):
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[to_email],
    )
    if html_body:
        email.attach_alternative(html_body, "text/html")
    email.send()