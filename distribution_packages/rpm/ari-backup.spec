%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name: ari-backup
Version: 0.9.2
Release: 1%{?dist}
Summary: A helpful wrapper around rdiff-backup
Group: Development/Languages
License: BSD
URL: https://github.com/jpwoodbu/ari-backup
Source0: https://github.com/jpwoodbu/%{name}/archive/v%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch: noarch
BuildRequires: python-setuptools
BuildRequires: rpm-python
Requires: crontabs
Requires: python-setuptools
Requires: PyYAML
Requires: rdiff-backup

%description
A helpful wrapper around rdiff-backup

%prep
%setup -q

%build
%{__python} setup.py build

%install
rm -rf %{buildroot}
%{__python} setup.py install -O1 --skip-build --root %{buildroot}

# Directories
mkdir -p %{buildroot}/%{_sysconfdir}/%{name}/
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
%config(noreplace) %{_sysconfdir}/%{name}/ari-backup.conf.yaml
%config(noreplace) %{_sysconfdir}/%{name}/jobs.d/*
%defattr(700,root,root,-)
%config %{_sysconfdir}/cron.daily/ari-backup
%doc README.mediawiki LICENSE.txt
