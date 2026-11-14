<?php
/** @var array<string, mixed> $config */

$config["use_https"] = true;
$config["proxy_whitelist"] = ["172.30.80.2"];
$config["imap_conn_options"] = [
    "ssl" => [
        "verify_peer" => true,
        "verify_peer_name" => true,
        "allow_self_signed" => false,
    ],
];
$config["smtp_conn_options"] = $config["imap_conn_options"];
