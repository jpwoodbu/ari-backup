%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name: ari-backup
Version: 1.0.10
Release: 1%{?dist}
Summary: A helpful wrapper around rdiff-backup
Group: Development/Languages
License: BSD
URL: https://github.com/jpwoodbu/ari-backup
Source0: https://github.com/jpwoodbu/%{name}/archive/%{version}.tar.gz
Patch0: ari-backup.change_default_destination.patch
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch: noarch
BuildRequires: python-setuptools
BuildRequires: rpm-python
Requires: crontabs
Requires: python-gflags
Requires: python-setuptools
Requires: PyYAML
Requires: rdiff-backup

%description
A helpful wrapper around rdiff-backup that allows backup jobs to be simple Python modules.


%prep
%setup -q

%patch0 -p0


%build
%{__python} setup.py build


%install
rm -rf %{buildroot}
%{__python} setup.py install -O1 --skip-build --root %{buildroot}

# Directories
mkdir -p %{buildroot}/%{_sharedstatedir}/%{name}
mkdir -p %{buildroot}/%{_sysconfdir}/%{name}/jobs.d
mkdir -p %{buildroot}/%{_sysconfdir}/cron.daily

# Configuration
cp -R include/etc/%{name}/* %{buildroot}/%{_sysconfdir}/%{name}

# Cron
cp include/cron/ari-backup %{buildroot}/%{_sysconfdir}/cron.daily/


%clean
rm -rf %{buildroot}


%files
# root
%defattr(-,root,root,-)
%{python_sitelib}/ari_backup
%{python_sitelib}/*.egg-info
%defattr(0600,root,root,0700)
%{_sysconfdir}/%{name}
%{_sysconfdir}/%{name}/jobs.d
%config(noreplace) %{_sysconfdir}/%{name}/ari-backup.conf.yaml
%config(noreplace) %{_sysconfdir}/%{name}/jobs.d/*
%defattr(0700,root,root,0700)
%config %{_sysconfdir}/cron.daily/ari-backup
%{_sharedstatedir}/%{name}
%doc README.md LICENSE.txt


%changelog
* Wed Oct 7 2015 Randy Barlow <randy@electronsweatshop.com> 1.0.10-1
- Initial release
