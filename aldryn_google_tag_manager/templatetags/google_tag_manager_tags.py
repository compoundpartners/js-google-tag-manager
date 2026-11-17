# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import json

from django.conf import settings
from django.template import Library
from django.utils.safestring import mark_safe
from html import unescape

register = Library()

# Divio serves every application from a shared *.aldryn.io domain, and aldryn.io
# is NOT on the Public Suffix List. Browsers therefore treat it as a single
# registrable domain, so GA4's default cookie_domain of "auto" resolves to
# ".aldryn.io" and every environment writes cookies that are then sent to every
# other environment -- test, live and every other client project alike. With
# 20-30 environments running at once that compounds until request headers
# outgrow the server's buffer (see JST06-55).
#
# Naming the suffix here is the only way to tell shared hosting apart from a
# real domain: it is a public suffix in all but registration, and no framework
# can know that for us. Add to this tuple if Divio introduces another one.
SHARED_HOST_SUFFIXES = ('aldryn.io',)


@register.inclusion_tag("aldryn_google_tag_manager/google_tag_manager.html")
def google_tag_manager(*args, **kwargs):
    if len(args) == 1 and args[0]:
        kwargs['tag_id'] = args[0]
    elif not 'tag_id' in kwargs and hasattr(settings, 'GOOGLE_TAG_MANAGER_ID'):
        kwargs['tag_id'] = settings.GOOGLE_TAG_MANAGER_ID
    return kwargs

@register.simple_tag
def data_layer(**kwargs):
    nonce = kwargs.pop('csp_nonce', '')
    if nonce:
        nonce = f' nonce="{nonce}"'
    data = []
    for key, value in kwargs.items():
        if value:
            value = '%s' % value
            data.append("'%s': '%s'" % (key.replace('_', '-'), unescape(value).replace("'", "\\'")))
    return mark_safe('''<script%s>
    var dataLayer = window.dataLayer = window.dataLayer || [];
    dataLayer.push({
        %s
    });
  </script>''' % (nonce, ', '.join(data)))

@register.simple_tag
def to_list_if_exists(*args):
    return [arg for arg in args if arg]


def resolve_cookie_domain(host):
    """Return the GA4 cookie_domain to use for `host`.

    On shared hosting every environment must get its own cookie jar, so the
    cookie is pinned to the exact host. Anywhere else we return "auto" and let
    Google resolve the registrable domain with its own public suffix list --
    that is what pairs www.example.com with example.com, and it handles every
    other subdomain shape correctly too.
    """
    # get_host() includes the port (":8000" in local development); a cookie
    # domain must never carry one. Trailing dots are legal in a Host header.
    host = host.split(':')[0].strip().rstrip('.').lower()
    for suffix in SHARED_HOST_SUFFIXES:
        # Suffix match on a label boundary, never a substring: "notaldryn.io"
        # and "aldryn.io.example.com" must not be treated as shared hosting.
        if host == suffix or host.endswith('.' + suffix):
            return host
    return 'auto'


@register.simple_tag(takes_context=True)
def gtm_cookie_domain(context):
    """Push cookie_domain into the data layer for the GA4 tag to read.

    MUST be rendered in <head> BEFORE the Google Tag Manager snippet. GTM reads
    the data layer as it initialises, so a push that happens later -- for
    instance from the data_layer tag at the end of <body> -- arrives after the
    GA4 tag has already fired, and the cookie is silently written to the wrong
    domain.
    """
    request = context.get('request')
    if request is None:
        # No request in context (e.g. a template rendered offline). Emitting
        # nothing leaves GTM on its own default rather than guessing a host.
        return ''
    domain = resolve_cookie_domain(request.get_host())
    # json.dumps gives a correctly quoted and escaped JavaScript string literal,
    # so a hostile Host header cannot break out of it.
    return mark_safe(
        '<script>window.dataLayer = window.dataLayer || [];'
        'window.dataLayer.push({"cookie_domain": %s});</script>' % json.dumps(domain)
    )
