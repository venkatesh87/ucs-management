# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin policy for the print quota settings
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

from ldap.filter import filter_format

from univention.admin.layout import Tab, Group
import univention.admin.syntax
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization
import univention.admin.uexceptions
import univention.debug
import string

from univention.admin.policy import (
	register_policy_mapping, policy_object_tab,
	requiredObjectClassesProperty, prohibitedObjectClassesProperty,
	fixedAttributesProperty, emptyAttributesProperty, ldapFilterProperty
)


translation = univention.admin.localization.translation('univention.admin.handlers.policies')
_ = translation.translate


class sharePrintQuotaFixedAttributes(univention.admin.syntax.select):
	name = 'sharePrintQuotaFixedAttributes'
	choices = [
		('univentionPrintQuotaGroups', _('Print quota for groups')),
		('univentionPrintQuotaUsers', _('Print quota for users')),
		('univentionPrintQuotaGroupsPerUsers', _('Print quota for groups per user'))
	]


module = 'policies/print_quota'
operations = ['add', 'edit', 'remove', 'search']

policy_oc = 'univentionPolicySharePrintQuota'
policy_apply_to = ["shares/printer", "shares/printergroup"]
policy_position_dn_prefix = "cn=printquota,cn=shares"

childs = 0
short_description = _('Policy: Print quota')
policy_short_description = _('Print Quota')
long_description = _('Print Quota for users/groups per printer')

options = {}

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
	'quotaGroups': univention.admin.property(
		short_description=_('Print quota for groups'),
		long_description=_('Soft and hard limits for each allowed group'),
		syntax=univention.admin.syntax.PrintQuotaGroup,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'quotaGroupsPerUsers': univention.admin.property(
		short_description=_('Print quota for groups per user'),
		long_description=_('Soft and hard limits for each member of allowed group'),
		syntax=univention.admin.syntax.PrintQuotaGroupPerUser,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'quotaUsers': univention.admin.property(
		short_description=_('Print quota for users'),
		long_description=_('Soft and hard limits for each allowed user'),
		syntax=univention.admin.syntax.PrintQuotaUser,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),

}
property_descriptions.update(dict([
	requiredObjectClassesProperty(),
	prohibitedObjectClassesProperty(),
	fixedAttributesProperty(syntax=sharePrintQuotaFixedAttributes),
	emptyAttributesProperty(syntax=sharePrintQuotaFixedAttributes),
	ldapFilterProperty(),
]))

layout = [
	Tab(_('General'), _('Print quota'), layout=[
		Group(_('General print quota settings'), layout=[
			'name',
			['quotaUsers', 'quotaGroupsPerUsers'],
			'quotaGroups'
		]),
	]),
	policy_object_tab(),
]


def unmapQuotaEntries(old):
	new = []
	for i in old:
		new.append(i.split(' ', 2))
	return new


def mapQuotaEntries(old):
	new = []
	for i in old:
		new.append(string.join(i, ' '))
	return new


mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('quotaGroups', 'univentionPrintQuotaGroups', mapQuotaEntries, unmapQuotaEntries)
mapping.register('quotaGroupsPerUsers', 'univentionPrintQuotaGroupsPerUsers', mapQuotaEntries, unmapQuotaEntries)
mapping.register('quotaUsers', 'univentionPrintQuotaUsers', mapQuotaEntries, unmapQuotaEntries)
register_policy_mapping(mapping)


class object(univention.admin.handlers.simplePolicy):
	module = module

	def _ldap_pre_create(self):
		super(object, self)._ldap_pre_create()
		self.check_entries()

	def _ldap_pre_modify(self):
		self.check_entries()

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionPolicy', 'univentionPolicySharePrintQuota'])]

	def check_entries(self):
		if self.hasChanged('quotaGroups') and self.info.get('quotaGroups'):
			for entry in self.info.get('quotaGroups'):
				group_dn = self.lo.searchDn(filter=filter_format('(&(objectClass=posixGroup)(cn=%s))', [entry[2]]))
				if len(group_dn) < 1 and entry[2] != 'root':
					raise univention.admin.uexceptions.notValidGroup(_('%s is not valid. ') % entry[2])

		if self.hasChanged('quotaUsers') and self.info.get('quotaUsers'):
			for entry in self.info.get('quotaUsers'):
				user_dn = self.lo.searchDn(filter=filter_format('(&(objectClass=posixAccount)(uid=%s))', [entry[2]]))
				if len(user_dn) < 1 and entry[2] != 'root':
					raise univention.admin.uexceptions.notValidUser(_('%s is not valid. ') % entry[2])


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionPolicySharePrintQuota')
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
	return 'univentionPolicySharePrintQuota' in attr.get('objectClass', [])
