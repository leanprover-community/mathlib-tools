from mathlibtools.file_status import PortStatus

status = PortStatus.deserialize_old(PortStatus.old_yaml())

print(status.serialize())
