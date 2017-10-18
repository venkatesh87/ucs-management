# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for printers
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

import re
from ldap.filter import filter_format

from univention.admin.layout import Tab, Group
import univention.admin.uldap
import univention.admin.syntax
import univention.admin.filter
import univention.admin.handlers
import univention.admin.handlers.settings.printermodel as printermodel
import univention.admin.handlers.settings.printeruri as printeruri
import univention.admin.localization

import univention.debug as ud
import univention.admin.uexceptions

translation = univention.admin.localization.translation('univention.admin.handlers.shares')
_ = translation.translate


class printerACLTypes(univention.admin.syntax.select):
	name = 'printerACLTypes'
	choices = [
		('allow all', _('Allow all users.')),
		('allow', _('Allow only chosen users/groups.')),
		('deny', _('Deny chosen users/groups.')),
	]


help_link = _('http://docs.univention.de/manual.html#print::shares')

module = 'shares/printer'
operations = ['add', 'edit', 'remove', 'search', 'move']

childs = 0
short_description = _('Printer share: Printer')
long_description = ''
options = {
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description='',
		syntax=univention.admin.syntax.printerName,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=False,
		identifies=True
	),
	'location': univention.admin.property(
		short_description=_('Location'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'description': univention.admin.property(
		short_description=_('Description'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'spoolHost': univention.admin.property(
		short_description=_('Spool host'),
		long_description='',
		syntax=univention.admin.syntax.ServicePrint_FQDN,
		multivalue=True,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'uri': univention.admin.property(
		short_description=_('Connection'),
		long_description='',
		syntax=univention.admin.syntax.PrinterURI,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'model': univention.admin.property(
		short_description=_('Printer model'),
		long_description='',
		syntax=univention.admin.syntax.PrinterDriverList,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'producer': univention.admin.property(
		short_description=_('Printer producer'),
		long_description='',
		syntax=univention.admin.syntax.PrinterProducerList,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'sambaName': univention.admin.property(
		short_description=_('Windows name'),
		long_description='',
		syntax=univention.admin.syntax.string_numbers_letters_dots_spaces,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False,
		unique=True
	),
	'setQuota': univention.admin.property(
		short_description=_('Enable quota support'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'pagePrice': univention.admin.property(
		short_description=_('Price per page'),
		long_description='',
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'jobPrice': univention.admin.property(
		short_description=_('Price per print job'),
		long_description='',
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'ACLtype': univention.admin.property(
		short_description=_('Access control'),
		long_description=_('Access list can allow or deny listed users and groups.'),
		syntax=printerACLTypes,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False,
		default="allow all"
	),
	'ACLUsers': univention.admin.property(
		short_description=_('Allowed/denied users'),
		long_description=_('For the given users printing is explicitly allowed or denied.'),
		syntax=univention.admin.syntax.UserDN,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False,
	),
	'ACLGroups': univention.admin.property(
		short_description=_('Allowed/denied groups'),
		long_description=_('For the given groups printing is explicitly allowed or denied.'),
		syntax=univention.admin.syntax.GroupDN,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False,
	),
}

layout = [
	Tab(_('General'), _('General settings'), layout=[
		Group(_('General printer share settings'), layout=[
			['name', 'sambaName'],
			'spoolHost',
			'uri',
			['producer', 'model'],
			['location', 'description'],
			['setQuota', ],
			['pagePrice', 'jobPrice'],
		]),
	]),
	Tab(_('Access control'), _('Access control for users and groups'), layout=[
		Group(_('Access control'), layout=[
			'ACLtype',
			'ACLUsers',
			'ACLGroups',
		]),
	]),
]


def boolToString(value):
	if value == '1':
		return ['yes']
	else:
		return ['no']


def stringToBool(value):
	if value[0].lower() == 'yes':
		return '1'
	else:
		return '0'


_AVAILABLE_PRINTER_SCHEMAS = []


def unmapPrinterURI(value):
	if not value:
		return ('', '')
	schema = ''
	dest = ''
	for sch in _AVAILABLE_PRINTER_SCHEMAS:
		if value[0].startswith(sch):
			schema = sch
			dest = value[0][len(sch):]
			break

	return (schema, dest)


def mapPrinterURI(value):
	return ''.join(value)


mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('location', 'univentionPrinterLocation', None, univention.admin.mapping.ListToString)
mapping.register('description', 'description', None, univention.admin.mapping.ListToString)
mapping.register('spoolHost', 'univentionPrinterSpoolHost')
mapping.register('uri', 'univentionPrinterURI', mapPrinterURI, unmapPrinterURI)
mapping.register('model', 'univentionPrinterModel', None, univention.admin.mapping.ListToString)
mapping.register('sambaName', 'univentionPrinterSambaName', None, univention.admin.mapping.ListToString)
mapping.register('setQuota', 'univentionPrinterQuotaSupport', None, univention.admin.mapping.ListToString)
mapping.register('pagePrice', 'univentionPrinterPricePerPage', None, univention.admin.mapping.ListToString)
mapping.register('jobPrice', 'univentionPrinterPricePerJob', None, univention.admin.mapping.ListToString)
mapping.register('ACLUsers', 'univentionPrinterACLUsers')
mapping.register('ACLGroups', 'univentionPrinterACLGroups')
mapping.register('ACLtype', 'univentionPrinterACLtype', None, univention.admin.mapping.ListToString)


class object(univention.admin.handlers.simpleLdap):
	module = module

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=[]):
		global _AVAILABLE_PRINTER_SCHEMAS
		# find the printer uris
		if not _AVAILABLE_PRINTER_SCHEMAS:
			printer_uris = printeruri.lookup(co, lo, '')
			_AVAILABLE_PRINTER_SCHEMAS = []
			for uri in printer_uris:
				_AVAILABLE_PRINTER_SCHEMAS.extend(uri['printeruri'])

		univention.admin.handlers.simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes=attributes)

	def open(self):
		# find the producer
		univention.admin.handlers.simpleLdap.open(self)
		models = printermodel.lookup(self.co, self.lo, 'printerModel="%s*' % self['model'])
		ud.debug(ud.ADMIN, ud.INFO, "printermodel: %s" % str(models))
		if not models or len(models) > 1:
			self['producer'] = []
		else:
			self['producer'] = models[0].dn

		self.save()

	def _ldap_pre_create(self):
		super(object, self)._ldap_pre_create()
		# cut off '/' at the beginning of the destination if it exists and protocol is file:/
		if self['uri'] and self['uri'][0] == 'file:/' and self['uri'][1][0] == '/':
			self['uri'][1] = re.sub(r'^/+', '', self['uri'][1])

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionPrinter'])]

	def _ldap_pre_modify(self):  # check for membership in a quota-printerclass
		# cut off '/' at the beginning of the destination if it exists and protocol is file:/
		if self['uri'] and self['uri'][0] == 'file:/' and self['uri'][1][0] == '/':
			self['uri'][1] = re.sub(r'^/+', '', self['uri'][1])
		if self.hasChanged('setQuota') and self.info['setQuota'] == '0':
			printergroups = self.lo.searchDn(filter=filter_format('(&(objectClass=univentionPrinterGroup)(univentionPrinterQuotaSupport=1)(univentionPrinterSpoolHost=%s))', [self.info['spoolHost'][0]]))
			group_cn = []
			for pg_dn in printergroups:
				member_list = self.lo.get(pg_dn, attr=['univentionPrinterGroupMember', 'cn'])
				for member_cn in member_list.get('univentionPrinterGroupMember', []):
					if member_cn == self.info['name']:
						group_cn.append(member_list['cn'][0])
			if len(group_cn) > 0:
				raise univention.admin.uexceptions.leavePrinterGroup(_('%(name)s is member of the following quota printer groups %(groups)s') % {'name': self.info['name'], 'groups': ', '.join(group_cn)})

	def _ldap_pre_remove(self):  # check for last member in printerclass
		printergroups = self.lo.searchDn(filter=filter_format('(&(objectClass=univentionPrinterGroup)(univentionPrinterSpoolHost=%s))', [self.info['spoolHost'][0]]))
		rm_attrib = []
		for pg_dn in printergroups:
			member_list = self.lo.search(base=pg_dn, attr=['univentionPrinterGroupMember', 'cn'])
			for member_cn in member_list[0][1]['univentionPrinterGroupMember']:
				if member_cn == self.info['name']:
					rm_attrib.append(member_list[0][0])
					if len(member_list[0][1]['univentionPrinterGroupMember']) < 2:
						raise univention.admin.uexceptions.emptyPrinterGroup(_('%(name)s is the last member of the printer group %(group)s. ') % {'name': self.info['name'], 'group': member_list[0][1]['cn'][0]})
		printergroup_module = univention.admin.modules.get('shares/printergroup')
		for rm_dn in rm_attrib:
			printergroup_object = univention.admin.objects.get(printergroup_module, None, self.lo, position='', dn=rm_dn)
			printergroup_object.open()
			printergroup_object['groupMember'].remove(self.info['name'])
			printergroup_object.modify()


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionPrinter'),
	])

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	for dn in lo.searchDn(unicode(filter), base, scope, unique, required, timeout, sizelimit):
		res.append(object(co, lo, None, dn))
	return res


def identify(dn, attr, canonical=0):

	return 'univentionPrinter' in attr.get('objectClass', [])
