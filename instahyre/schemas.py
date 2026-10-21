"""Marshmallow request schemas for every /instahyre/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Instahyre resolvers (refs.py). Every schema's load() output is the
kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a job id OR any Instahyre job link;
`company` an employer id, a /jobs-at-<slug>/ link or slug, or a company
name; `location` the site's own picker names (case-insensitive, alternate
spellings and "remote" accepted, comma list); `job_function` /
`job_category` / `industry` ids, slugs or names (comma lists).
"""
from marshmallow import ValidationError, fields, validate

from schema_fields import BaseSchema, ChoiceField, Flag, PageField, QueryField, RefField, StrippedString
from instahyre import refdata, refs


def _max_length(n):
    """validate.Length(max=n) that tolerates the None StrippedString returns
    for an empty value (marshmallow runs validators on it; len(None) is a 500)."""
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class _OptionalRef(RefField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class JobListField(RefField):
    resolver = staticmethod(refs.resolve_jobs)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class LocationListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_locations)


class JobFunctionListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_job_functions)


class JobCategoryListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_job_categories)


class IndustryListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_industries)


class CompanyNamesField(_OptionalRef):
    resolver = staticmethod(refs.resolve_company_names)


class ExperienceYearsField(fields.Integer):
    """Years of experience the candidate has: the site keeps jobs whose band
    admits it (0 = jobs for freshers)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Range(min=0, max=refdata.MAX_EXPERIENCE_YEARS))
        super().__init__(strict=False, **kwargs)


# ---- jobs ----------------------------------------------------------------------------------------------------

class _JobFilters(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(200))
    location = LocationListField()
    experience_years = ExperienceYearsField()
    job_type = ChoiceField(list(refdata.JOB_TYPES))
    company_size = ChoiceField(list(refdata.COMPANY_SIZES))
    job_function = JobFunctionListField()
    job_category = JobCategoryListField()
    industry = IndustryListField()
    company = CompanyNamesField()


class JobSearchSchema(_JobFilters):
    page = PageField(max_page=refdata.MAX_PAGE)
    include_details = Flag(load_default=False)


class JobStatsSchema(_JobFilters):
    pass


class JobSchema(BaseSchema):
    job = JobField()
    include_company = Flag(load_default=True)


class JobBatchSchema(BaseSchema):
    jobs = JobListField()
    include_company = Flag(load_default=False)


class SimilarJobsSchema(BaseSchema):
    job = JobField()


# ---- companies ----------------------------------------------------------------------------------------------------

class CompanySchema(BaseSchema):
    company = CompanyField()
    include_jobs = Flag(load_default=True)


class CompanyJobsSchema(BaseSchema):
    company = CompanyField()
    page = PageField(max_page=refdata.MAX_PAGE)
    query = StrippedString(required=False, load_default=None, validate=_max_length(200))
    location = LocationListField()
    job_type = ChoiceField(list(refdata.JOB_TYPES))
    experience_years = ExperienceYearsField()


class CompanySearchSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=50))


# ---- lookups ------------------------------------------------------------------------------------------------------------

class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100)
    type = ChoiceField(["skills", "companies", "locations"], load_default="skills")
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=50))


class EmptySchema(BaseSchema):
    pass
