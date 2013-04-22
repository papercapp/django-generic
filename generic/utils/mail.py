import copy
import logging
from django.conf import settings
from django.core import mail
from django.template import RequestContext
from django.template.loader import render_to_string
from django.test import RequestFactory

logger = logging.getLogger(__name__)

dummy_request = RequestFactory().request()

class EmailMessage(mail.EmailMessage):
    """ Generic feature additions to the standard EmailMessage """
    def __init__(self, *args, **kwargs):
        # template-rendering shortcuts:
        self.template_name = kwargs.pop('template_name', None)
        self.context = kwargs.pop('context', None)
        self.request = kwargs.pop('request', dummy_request)
        self.use_context_processors = kwargs.pop('use_context_processors', True)

        # where there are multiple recipients in the 'to' field, send
        # each one as a separate email to avoid exposing third-party addresses
        self.send_separately = kwargs.pop('send_separately', False)

        super(EmailMessage, self).__init__(*args, **kwargs)

        if self.template_name and not self.body:
            if self.use_context_processors:
                self.context = RequestContext(self.request).update(self.context)
            self.body = render_to_string(self.template_name, self.context)

    def send(self, fail_silently=False):
        if self.send_separately:
            messages = []
            for address in self.to:
                message = copy.copy(self) # no need for deepcopy here?
                message.to = [address]
                messages.append(message)
            return self.get_connection(fail_silently).send_messages(messages)
        else:
            return super(EmailMessage, self).send(fail_silently)


class FallbackEmailMessage(EmailMessage):
    """ EmailMessage which sends to settings.ADMINS if found recipientless """
    def __init__(self, *args, **kwargs):
        self.fallback_addresses = kwargs.pop('fallback_addresses', None)
        self.fallback_prefix = kwargs.pop('fallback_prefix', '[Fallback] ')
        self.fallback_body_prefix = kwargs.pop(
            'fallback_body_prefix', (
                'WARNING: this message has been sent to ADMINS because the '
                'intended recipient list was empty.'
            )
        )
        super(FallbackEmailMessage, self).__init__(*args, **kwargs)

    def get_fallback_addresses(self):
        if self.fallback_addresses is None:
            return dict(settings.ADMINS).values()
        else:
            return self.fallback_addresses

    def send(self, fail_silently=False):
        if not self.recipients():
            self.send_separately = False
            if not self.fallback_addresses:
                logger.error(
                    'No fallback recipients for message: %s' % self.subject)
            self.to = self.fallback_addresses
            self.subject = u''.join([self.fallback_prefix, self.subject])
            self.body = u'\n'.join([self.fallback_body_prefix, self.body])
        return super(FallbackEmailMessage, self).send(fail_silently)
