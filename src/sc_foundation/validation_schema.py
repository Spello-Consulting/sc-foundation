"""Validation schema for YAML configuration files."""

yaml_config_validation = {
    "Files": {
        "type": "dict",
        "schema": {
            "LogfileName": {"type": "string", "required": False, "nullable": True},
            "LogfileMaxLines": {"type": "number", "required": False, "nullable": True, "min": 0, "max": 100000},
            "TimestampFormat": {"type": "string", "required": False, "nullable": True},
            "LogProcessID": {"type": "boolean", "required": False, "nullable": True},
            "LogThreadID": {"type": "boolean", "required": False, "nullable": True},
            "LogfileVerbosity": {"type": "string", "required": True, "allowed": ["none", "error", "warning", "summary", "detailed", "debug", "all"]},
            "ConsoleVerbosity": {"type": "string", "required": True, "allowed": ["error", "warning", "summary", "detailed", "debug"]},
        },
    },
    "Email": {
        "type": "dict",
        "schema": {
            "EnableEmail": {"type": "boolean", "required": False, "nullable": True},
            "SMTPServer":  {"type": "string", "required": False, "nullable": True},
            "SMTPPort": {"type": "number", "required": False, "nullable": True, "min": 25, "max": 10000},
            "SMTPUsername": {"type": "string", "required": False, "nullable": True},
            "SMTPPassword": {"type": "string", "required": False, "nullable": True},
            "FromEmail": {"type": "string", "required": False, "nullable": True},
            "SendEmailsTo": {"type": "string", "required": False, "nullable": True},
            "SubjectPrefix": {"type": "string", "required": False, "nullable": True},
        },
    },
    "HeartbeatMonitor": {
        "type": "dict",
        "required": False,
        "schema": {
            "Enable": {"type": "boolean", "required": False, "nullable": True},
            "WebsiteURL": {"type": "string", "required": False, "nullable": True},
            "HeartbeatTimeout": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 60},
            "Frequency": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 3600},
        },
    },
    "Location": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "GoogleMapsURL": {"type": "string", "required": False, "nullable": True},
            "Timezone": {"type": "string", "required": False, "nullable": True},
            "Latitude": {"type": "number", "required": False, "nullable": True},
            "Longitude": {"type": "number", "required": False, "nullable": True},
        },
    }
}
