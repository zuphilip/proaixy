# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render, get_object_or_404
from django.template import RequestContext, loader
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist

from oaipmh.datestamp import tolerant_datestamp_to_datetime
from oaipmh.error import DatestampError

from datetime import datetime

from oai.tasks import *
from oai.models import *
from oai.utils import to_kv_pairs, OaiRequestError
from oai.settings import *

def handleListQuery(request, context, queryType, parameters, offset=0):
    if queryType == 'ListRecords' or queryType == 'ListIdentifiers':
        matches = OaiRecord.objects.filter(**parameters)
    elif queryType == 'ListSets':
        matches = OaiSet.objects.all()
    else:
        raise OaiRequestError('badArgument', 'Illegal verb.')
    matches = list(matches[offset:(offset+RESULTS_LIMIT+1)])
    count = len(matches)
    # Should we create a resumption token?
    if count > RESULTS_LIMIT:
        token = createResumptionToken(queryType, parameters, offset+RESULTS_LIMIT, count)
        context['token'] = token
    context['matches'] = matches
    return render(request, 'oai/'+queryType+'.xml', context, content_type='text/xml')


def createResumptionToken(queryType, queryParameters, offset, totalCount):
    token = ResumptionToken(queryType=queryType, offset=offset,
            cursor=offset-RESULTS_LIMIT, total_count=totalCount)
    if 'format' in queryParameters:
        token.metadataPrefix = queryParameters['format']
    if 'timestamp__gte' in queryParameters:
        token.fro = queryParameters['timestamp__gte']
    if 'timestamp__lte' in queryParameters:
        token.until = queryParameters['timestamp__lte']
    if 'sets' in queryParameters:
        token.set = queryParameters['sets']
    token.save()
    token.genkey()
    return token

def resumeRequest(context, request, queryType, key):
    try:
        token = ResumptionToken.objects.get(queryType=queryType, key=key)
    except ObjectDoesNotExist:
        raise OaiRequestError('badResumptionToken', 'This resumption token is invalid: "'+key+'", "'+queryType+'"', context, request)
    parameters = dict()
    parameters['format'] = token.metadataPrefix
    if token.set:
        parameters['sets'] = token.set
    if token.fro:
        parameters['timestamp__gte'] = token.fro
    if token.until:
        parameters['timestamp__lte'] = token.until
    return handleListQuery(request, context, queryType, parameters, token.offset)
    


