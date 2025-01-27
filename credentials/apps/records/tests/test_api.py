"""
Tests for the `api.py` file of the Records Django app.
"""
import datetime

from django.contrib.contenttypes.models import ContentType
from django.template.defaultfilters import slugify
from django.test import TestCase

from credentials.apps.catalog.tests.factories import (
    CourseFactory,
    CourseRunFactory,
    OrganizationFactory,
    PathwayFactory,
    ProgramFactory,
)
from credentials.apps.core.tests.factories import UserFactory
from credentials.apps.core.tests.mixins import SiteMixin
from credentials.apps.credentials.api import get_credential_dates
from credentials.apps.credentials.tests.factories import (
    CourseCertificateFactory,
    ProgramCertificateFactory,
    UserCredentialFactory,
)
from credentials.apps.records.api import (
    _does_awarded_program_cert_exist_for_user,
    _get_shared_program_cert_record_data,
    _get_transformed_grade_data,
    _get_transformed_learner_data,
    _get_transformed_pathway_data,
    _get_transformed_program_data,
)
from credentials.apps.records.constants import UserCreditPathwayStatus
from credentials.apps.records.tests.factories import (
    ProgramCertRecordFactory,
    UserCreditPathwayFactory,
    UserGradeFactory,
)


class ApiTests(SiteMixin, TestCase):
    """
    Tests for the utility functions of the Records Django app's `api.py` file.
    """

    def setUp(self):
        super().setUp()
        self.COURSE_CERTIFICATE_CONTENT_TYPE = ContentType.objects.get(
            app_label="credentials", model="coursecertificate"
        )
        self.PROGRAM_CERTIFICATE_CONTENT_TYPE = ContentType.objects.get(
            app_label="credentials", model="programcertificate"
        )
        # create the user to award the certificate(s) to
        self.user = UserFactory()
        # create the organization for the program
        self.org = OrganizationFactory.create(name="TestOrg1")
        # create courses, course-runs, and course certificate configurations for our tests
        self.course = CourseFactory.create(site=self.site)
        self.course_runs = CourseRunFactory.create_batch(2, course=self.course)
        self.course_cert_configs = [
            CourseCertificateFactory.create(
                course_id=course_run.key,
                site=self.site,
            )
            for course_run in self.course_runs
        ]
        # create program and program certificate configuration for our tests
        self.program = ProgramFactory(
            title="TestProgram1",
            course_runs=[self.course_runs[0], self.course_runs[1]],
            authoring_organizations=[self.org],
            site=self.site,
        )
        self.program_cert_config = ProgramCertificateFactory.create(program_uuid=self.program.uuid, site=self.site)
        # generate some grade data in the course-runs for our test user
        self.grade_low = UserGradeFactory(
            username=self.user.username,
            course_run=self.course_runs[0],
            letter_grade="C",
            percent_grade=0.75,
        )
        self.grade_high = UserGradeFactory(
            username=self.user.username,
            course_run=self.course_runs[1],
            letter_grade="A",
            percent_grade=1.0,
        )
        # award course certificate to our test user
        self.course_certificiate_credentials = [
            UserCredentialFactory.create(
                username=self.user.username,
                credential_content_type=self.COURSE_CERTIFICATE_CONTENT_TYPE,
                credential=course_cert_config,
            )
            for course_cert_config in self.course_cert_configs
        ]
        self.program_certificate_credential = UserCredentialFactory.create(
            username=self.user.username,
            credential_content_type=self.PROGRAM_CERTIFICATE_CONTENT_TYPE,
            credential=self.program_cert_config,
        )
        # setup a credit pathway and then add a pathway record for our user
        self.pathway = PathwayFactory(site=self.site, programs=[self.program])
        UserCreditPathwayFactory(user=self.user, pathway=self.pathway, status=UserCreditPathwayStatus.SENT)
        # create a shared program cert record for our user
        self.shared_program_cert_record = ProgramCertRecordFactory(
            uuid=self.program.uuid, program=self.program, user=self.user
        )

    def _assert_results(self, expected_result, result):
        """
        Utility function that compares two dictionaries and verifies the results generated by our code matches the
        expected results.
        """
        expected_keys = expected_result.keys()
        for key in expected_keys:
            assert result[key] == expected_result[key]

    def test_does_awarded_program_cert_exist_for_user_with_cert(self):
        """
        Test that verifies the functionality of the `_does_awarded_program_cert_exist_for_user` utility function when a
        certificate exists for the user.
        """
        result = _does_awarded_program_cert_exist_for_user(self.program, self.user)
        assert result is True

    def test_does_awarded_program_cert_exist_for_user_no_cert(self):
        """
        Test that verifies the functionality of the `_does_awarded_program_cert_exist_for_user` utility function when a
        certificate exists for the user.
        """
        self.program_certificate_credential.revoke()

        result = _does_awarded_program_cert_exist_for_user(self.program, self.user)
        assert result is False

    def test__get_transformed_learner_data(self):
        """
        Test that verifies the functionality of the `_get_transformed_learner_data` utility function.
        """
        expected_result = {
            "full_name": self.user.get_full_name(),
            "username": self.user.username,
            "email": self.user.email,
        }

        result = _get_transformed_learner_data(self.user)
        self._assert_results(expected_result, result)

    def test_get_transformed_program_data(self):
        """
        Test that verifies the functionality of the `_get_transformed_program_data` utiltiy function.
        """
        last_updated = datetime.datetime.now()

        expected_result = {
            "name": self.program.title,
            "type": slugify(self.program.type),
            "type_name": self.program.type,
            "completed": True,
            "empty": True,
            "last_updated": last_updated.isoformat(),
            "school": ", ".join(self.program.authoring_organizations.values_list("name", flat=True)),
        }

        result = _get_transformed_program_data(self.program, self.user, {}, last_updated)
        self._assert_results(expected_result, result)

    def test_get_transformed_pathway_data(self):
        """
        Test that verifies the functionality of the `_get_transformed_pathway_data` utility function.
        """
        expected_result = {
            "name": self.pathway.name,
            "id": self.pathway.id,
            "status": UserCreditPathwayStatus.SENT,
            "is_active": True,
            "pathway_type": self.pathway.pathway_type,
        }

        result = _get_transformed_pathway_data(self.program, self.user)
        self._assert_results(expected_result, result[0])

    def test_get_transformed_grade_data(self):
        """
        Test that verifies the functionality of the `_get_transformed_grade_data` utility function.
        """
        expected_issue_date = get_credential_dates(self.course_certificiate_credentials[1], False)
        expected_result = {
            "name": self.course_runs[1].title,
            "school": ",".join(self.course.owners.values_list("name", flat=True)),
            "attempts": 2,
            "course_id": self.course_runs[1].key,
            "issue_date": expected_issue_date.isoformat(),
            "percent_grade": 1.0,
            "letter_grade": "A",
        }

        expected_highest_attempt_dict = {self.course: self.grade_high}

        result, highest_attempt_dict, last_updated = _get_transformed_grade_data(self.program, self.user)
        self._assert_results(expected_result, result[0])
        self._assert_results(expected_highest_attempt_dict, highest_attempt_dict)
        assert float(highest_attempt_dict.get(self.course).percent_grade) == self.grade_high.percent_grade
        assert expected_issue_date == last_updated

    def test_get_shared_program_cert_record_data(self):
        """
        Test that verifies the functionality of the `_get_shared_program_cert_record_data` utility function.
        """
        result = _get_shared_program_cert_record_data(self.program, self.user)
        assert result == str(self.shared_program_cert_record.uuid)

    def test_get_shared_program_cert_record_data_record_dne(self):
        """
        Test that verifies the functionality of the `_get_shared_program_cert_record_data` utility function when a
        shared record does not exist.
        """
        self.shared_program_cert_record.delete()

        result = _get_shared_program_cert_record_data(self.program, self.user)
        assert result is None
