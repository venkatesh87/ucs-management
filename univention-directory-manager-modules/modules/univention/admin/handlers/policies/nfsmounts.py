# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin policy for nfs mounts
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


class ldapServerFixedAttributes(univention.admin.syntax.select):
	name = 'updateFixedAttributes'
	choices = [
		('univentionNFSMounts', _('Mount NFS shares')),
	]


module = 'policies/nfsmounts'
operations = ['add', 'edit', 'remove', 'search']

policy_oc = 'univentionPolicyNFSMounts'
policy_apply_to = ["computers/domaincontroller_master", "computers/domaincontroller_backup", "computers/domaincontroller_slave", "computers/memberserver", "computers/managedclient", "computers/mobileclient"]
policy_position_dn_prefix = "cn=nfsmounts"

childs = 0
short_description = _('Policy: NFS mounts')
policy_short_description = _('NFS mounts')
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
	'nfsMounts': univention.admin.property(
		short_description=_('NFS shares to mount'),
		long_description='',
		syntax=univention.admin.syntax.nfsMounts,
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
	fixedAttributesProperty(syntax=ldapServerFixedAttributes),
	emptyAttributesProperty(syntax=ldapServerFixedAttributes),
	ldapFilterProperty(),
]))

layout = [
	Tab(_('General'), _('Basic settings'), layout=[
		Group(_('General NFS mounts settings'), layout=[
			'name',
			'nfsMounts'
		]),
	]),
	policy_object_tab()
]


def unmapMounts(old):
	return map(lambda x: x.split(' '), old)


def mapMounts(old):
	return map(lambda x: ' '.join(x), old)


mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('nfsMounts', 'univentionNFSMounts', mapMounts, unmapMounts)
register_policy_mapping(mapping)


class object(univention.admin.handlers.simplePolicy):
	module = module

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionPolicy', 'univentionPolicyNFSMounts'])]


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionPolicyNFSMounts')
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
	return 'univentionPolicyNFSMounts' in attr.get('objectClass', [])
