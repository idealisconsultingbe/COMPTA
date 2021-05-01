import logging
import traceback
import json
_logger = logging.getLogger(__name__)

class SkippedException(Exception):
    pass
class FailedException(Exception):
    pass

class Log():

    def reset(self, date, sequence, entity, key, data):
        self.messages = []
        self.status = False
        self.date = date
        self.sequence = sequence
        self.entity = entity
        self.key = key
        self.data = data
        self.traceback = False

    def skipped(self, message):
        self.messages.append('<li><b style="color:gray">SKIPPED</b> %s </li>' % message)
        self.status = 'skipped'
        raise SkippedException()

    def info(self, message):
        self.messages.append('<li><b style="color:green">INFO</b> %s </li>' % message)

    def warning(self, message):
        self.messages.append('<li><b style="color:orange">WARNING</b> %s </li>' % message)
        self.status = 'warning'

    def error(self, message):
        self.messages.append('<li><b style="color:red">ERROR</b> %s </li>' % message)
        self.status = 'error'

    def failed(self, message, raise_exc=True):
        self.messages.append('<li><b style="color:red">FAILED</b> %s </li>' % message)
        self.status = 'failed'
        _logger.info(message)
        #self.traceback = traceback.print_exc()
        # print(self.traceback)
        if raise_exc:
            raise FailedException()

    def done(self):
        self.status = self.status or 'success'

    def get_message(self):
        return "<ul>%s</ul>" % ''.join(self.messages)

    def get_create_vals(self):
        return {
            'sync_message': self.get_message(),
            'sync_date': self.date,
            'sync_sequence': self.sequence,
            'efficy_entity': self.entity,
            'efficy_key': self.key,
            'sync_data': self.data,
            'sync_status': self.status,
            'sync_traceback': self.traceback
        }

