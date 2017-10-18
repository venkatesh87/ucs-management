# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin policy for the password history
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

import univention.debug

from univention.admin.policy import (
	register_policy_mapping, policy_object_tab,
	requiredObjectClassesProperty, prohibitedObjectClassesProperty,
	fixedAttributesProperty, emptyAttributesProperty, ldapFilterProperty
)


translation = univention.admin.localization.translation('univention.admin.handlers.policies')
_ = translation.translate


class pwhistoryFixedAttributes(univention.admin.syntax.select):
	name = 'pwhistoryFixedAttributes'
	choices = [
		('univentionPWHistoryLen', _('History length')),
		('univentionPWExpiryInterval', _('Password expiry interval')),
		('univentionPWLength', _('Password length'))
	]


module = 'policies/pwhistory'
operations = ['add', 'edit', 'remove', 'search']

policy_oc = 'univentionPolicyPWHistory'
policy_apply_to = ["users/user"]
policy_position_dn_prefix = "cn=pwhistory,cn=users"
childs = 0
short_description = _('Policy: Passwords')
policy_short_description = _('Passwords')
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
	'length': univention.admin.property(
		short_description=_('History length'),
		long_description=_('This number indicates after how many changes the user may reuse the old password again'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'expiryInterval': univention.admin.property(
		short_description=_('Password expiry interval'),
		long_description=_('Number of days after which the password has to be changed'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'pwLength': univention.admin.property(
		short_description=_('Password length'),
		long_description=_('Minimal amount of characters'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'pwQualityCheck': univention.admin.property(
		short_description=_('Password quality check'),
		long_description=_('Enables/disables password quality checks for example dictionary entries'),
		syntax=univention.admin.syntax.TrueFalseUp,
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
	fixedAttributesProperty(syntax=pwhistoryFixedAttributes),
	emptyAttributesProperty(syntax=pwhistoryFixedAttributes),
	ldapFilterProperty(),
]))

layout = [
	Tab(_('General'), _('Passwords'), layout=[
		Group(_('General passwords settings'), layout=[
			'name',
			'pwLength',
			'expiryInterval',
			'length',
			'pwQualityCheck',
		]),
	]),
	policy_object_tab()
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('length', 'univentionPWHistoryLen', None, univention.admin.mapping.ListToIntToString)
mapping.register('expiryInterval', 'univentionPWExpiryInterval', None, univention.admin.mapping.ListToIntToString)
mapping.register('pwLength', 'univentionPWLength', None, univention.admin.mapping.ListToIntToString)
mapping.register('pwQualityCheck', 'univentionPWQualityCheck', None, univention.admin.mapping.ListToString)
register_policy_mapping(mapping)


class object(univention.admin.handlers.simplePolicy):
	module = module

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionPolicy', 'univentionPolicyPWHistory'])]


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionPolicyPWHistory')
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
	return 'univentionPolicyPWHistory' in attr.get('objectClass', [])
