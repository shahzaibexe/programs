# pylint: disable=missing-docstring
import logging

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction
from edx_rest_api_client.client import EdxRestApiClient

from programs.apps.programs.models import Organization


logger = logging.getLogger(__name__)


class ForcedRollback(Exception):
    pass


class Command(BaseCommand):
    help = 'Sync organization data from the LMS.'
    client = None
    page = 1
    org_count = 0
    new_org_count = 0

    def add_arguments(self, parser):
        parser.add_argument(
            'access_token',
            help='OAuth 2.0 access token used to authenticate against LMS APIs.'
        )

        parser.add_argument(
            '-c', '--commit',
            action='store_true',
            dest='commit',
            default=False,
            help='Save organization data to the database.'
        )

    def _get_data(self):
        while self.page:
            data = self.client.organizations.get(page=self.page, page_size=settings.ORGANIZATIONS_API_PAGE_SIZE)

            if not self.org_count:
                self.org_count = data['count']

            orgs = data['results']
            logger.info('Retrieved %d organizations.', len(orgs))

            for org in orgs:
                if org['active']:
                    fields = {
                        'key': org['short_name'],
                        'display_name': org['name']
                    }

                    __, created = Organization.objects.get_or_create(**fields)
                    if created:
                        self.new_org_count += 1

            if data['next']:
                self.page += 1
            else:
                self.page = None

    def handle(self, *args, **options):
        access_token = options.get('access_token')
        commit = options.get('commit')

        self.client = EdxRestApiClient(settings.ORGANIZATIONS_API_URL_ROOT, oauth_access_token=access_token)

        logger.info('Retrieving organization data from %s.', settings.ORGANIZATIONS_API_URL_ROOT)

        try:
            with transaction.atomic():
                self._get_data()

                logger.info(
                    'Retrieved %d organizations from %s, %d of which were new.',
                    self.org_count,
                    settings.ORGANIZATIONS_API_URL_ROOT,
                    self.new_org_count
                )

                if not commit:
                    raise ForcedRollback('No data has been saved. To save data, pass the -c or --commit flags.')
        except ForcedRollback as e:
            logger.info(e)