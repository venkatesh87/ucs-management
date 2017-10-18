# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin policy for the DHCP statements
#
# Copyright 2004-2017 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

from univention.admin.layout import Tab, Group
import univention.admin.syntax
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization

from univention.admin.policy import (
	register_policy_mapping, policy_object_tab,
	requiredObjectClassesProperty, prohibitedObjectClassesProperty,
	fixedAttributesProperty, emptyAttributesProperty, ldapFilterProperty
)


translation = univention.admin.localization.translation('univention.admin.handlers.policies')
_ = translation.translate


class dhcp_statementsFixedAttributes(univention.admin.syntax.select):
	name = 'dhcp_statementsFixedAttributes'
	choices = [
		('univentionDhcpAuthoritative', _('Authoritative')),
		('univentionDhcpBootUnknownClients', _('Boot unknown clients')),
		('univentionDhcpPingCheck', _('Ping check')),
		('univentionDhcpGetLeaseHostnames', _('Add hostnames to leases')),
		('univentionDhcpServerIdentifier', _('Server identifier')),
		('univentionDhcpServerName', _('Server name')),
	]


module = 'policies/dhcp_statements'
operations = ['add', 'edit', 'remove', 'search']

policy_oc = "univentionPolicyDhcpStatements"
policy_apply_to = ["dhcp/host", "dhcp/pool", "dhcp/service", "dhcp/subnet", "dhcp/sharedsubnet", "dhcp/shared"]
policy_position_dn_prefix = "cn=statements,cn=dhcp"
policies_group = "dhcp"
childs = 0
short_description = _('Policy: DHCP statements')
policy_short_description = _('DHCP statement')
long_description = ''
options = {
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description='',
		syntax=univention.admin.syntax.policyName,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=False,
		identifies=True,
	),
	'authoritative': univention.admin.property(
		short_description=_('Authoritative'),
		long_description=_('Send DHCPNAK messages to misconfigured clients. Disabled by default.'),
		syntax=univention.admin.syntax.booleanNone,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'boot-unknown-clients': univention.admin.property(
		short_description=_('Boot unknown clients'),
		long_description=_('Enable clients for which there is no host declaration to obtain IP addresses. Allow and deny statements within pool declarations will still be respected.'),
		syntax=univention.admin.syntax.TrueFalse,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'pingCheck': univention.admin.property(
		short_description=_('Ping check'),
		long_description=_('First send an ICMP Echo request (a ping) when considering dynamically allocating an IP address. Should only be disabled if the delay of one second introduced by this is a problem for a client.'),
		syntax=univention.admin.syntax.TrueFalse,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'getLeaseHostnames': univention.admin.property(
		short_description=_('Add hostnames to leases'),
		long_description=_('Look up the domain name corresponding to the IP address of each address in the lease pool and use that address for the DHCP hostname option. Disabled by default.'),
		syntax=univention.admin.syntax.TrueFalse,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'serverIdentifier': univention.admin.property(
		short_description=_('Server identifier'),
		long_description=_('The IP address identifying the DHCP server that should be used by the clients. Use this only if auto-detection fails for servers with multiple IP addresses.'),
		syntax=univention.admin.syntax.hostOrIP,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'serverName': univention.admin.property(
		short_description=_('Server name'),
		long_description=_('Define the name of the DHCP server'),
		syntax=univention.admin.syntax.hostName,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
}
property_descriptions.update(dict([
	requiredObjectClassesProperty(),
	prohibitedObjectClassesProperty(),
	fixedAttributesProperty(syntax=dhcp_statementsFixedAttributes),
	emptyAttributesProperty(syntax=dhcp_statementsFixedAttributes),
	ldapFilterProperty(),
]))

layout = [
	Tab(_('DHCP statements'), _('Miscellaneous DHCP statements'), layout=[
		Group(_('General DHCP statements settings'), layout=[
			'name',
			['authoritative', 'boot-unknown-clients'],
			['pingCheck', 'getLeaseHostnames'],
			['serverIdentifier', 'serverName']
		]),
	]),
	policy_object_tab()
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('authoritative', 'univentionDhcpAuthoritative', None, univention.admin.mapping.ListToString)
mapping.register('boot-unknown-clients', 'univentionDhcpBootUnknownClients', None, univention.admin.mapping.ListToString)
mapping.register('pingCheck', 'univentionDhcpPingCheck', None, univention.admin.mapping.ListToString)
mapping.register('getLeaseHostnames', 'univentionDhcpGetLeaseHostnames', None, univention.admin.mapping.ListToString)
mapping.register('serverIdentifier', 'univentionDhcpServerIdentifier', None, univention.admin.mapping.ListToString)
mapping.register('serverName', 'univentionDhcpServerName', None, univention.admin.mapping.ListToString)
register_policy_mapping(mapping)


class object(univention.admin.handlers.simplePolicy):
	module = module

	def _ldap_addlist(self):
		return [
			('objectClass', ['top', 'univentionPolicy', 'univentionPolicyDhcpStatements'])
		]


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionPolicyDhcpStatements'),
	])

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	try:
		for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
			res.append(object(co, lo, None, dn, attributes=attrs))
	except:
		pass
	return res


def identify(dn, attr, canonical=0):

	return 'univentionPolicyDhcpStatements' in attr.get('objectClass', [])
