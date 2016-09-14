<?php

date_default_timezone_set('America/New_York');

if (!isset($_REQUEST['search']))
  exit(0);

$db = new mysqli('localhost', 'condor_read', '', 'condor_history');

$stmt = $db->prepare('SELECT MAX(`instance`) FROM `job_clusters`');
$stmt->bind_result($instance);
$stmt->execute();
$stmt->fetch();
$stmt->close();

$data = array();

if ($_REQUEST['search'] == 'users') {
  $stmt = $db->prepare('SELECT `name` FROM `users` WHERE `user_id` != 0');
  $stmt->bind_result($name);
  $stmt->execute();
  while ($stmt->fetch())
    $data[] = array("name" => $name);
  $stmt->close();
}
else if ($_REQUEST['search'] == 'clusters') {
  $users = $_REQUEST['users'];
  $cmds = $_REQUEST['cmds'];
  $ids = $_REQUEST['ids'];
  $begin = $_REQUEST['begin'];
  $end = $_REQUEST['end'];

  if (count($users) == 0 && count($cmds) == 0) {
    echo json_encode($data);
    exit(0);
  }

  if (is_array($users)) {
    $quoted_users = array();
    foreach ($users as $user)
      $quoted_users[] = sprintf("'%s'", $db->real_escape_string($user));
  }
  else if ($users != "")
    $quoted_users = array(sprintf("'%s'", $db->real_escape_string($users)));

  if (is_array($cmds)) {
    $quoted_cmds = array();
    foreach ($cmds as $cmd) {
      if (strlen($cmd) != 0)
        $quoted_cmds[] = sprintf("'%s'", $db->real_escape_string($cmd));
    }
  }
  else if ($cmds != "")
    $quoted_cmds = array(sprintf("'%s'", $db->real_escape_string($cmds)));

  if (is_array($ids)) {
    $quoted_ids = array();
    foreach ($ids as $id) {
      $s = '' . $id;
      if (strlen($s) != 0)
        $quoted_ids[] = sprintf("%s", $db->real_escape_string('' . $s));
    }
  }
  else if ('' . $ids != '')
    $quoted_ids = array(sprintf("%s", $db->real_escape_string('' . $s)));

  $tm = strptime($begin, '%Y/%m/%d');
  if ($tm !== false)
    $begin_ts = mktime(0, 0, 0, $tm['tm_mon'] + 1, $tm['tm_mday'], $tm['tm_year'] + 1900);
  else
    $begin_ts = 0;

  $tm = strptime($end, '%Y/%m/%d');
  if ($tm !== false)
    $end_ts = mktime(0, 0, 0, $tm['tm_mon'] + 1, $tm['tm_mday'], $tm['tm_year'] + 1900) + 3600 * 24;
  else
    $end_ts = 0;

  $query = 'SELECT c.`cluster_id`, u.`name`, c.`cmd`, c.`submit_time`, COUNT(j.`proc_id`)';
  $query .= ' FROM `job_clusters` AS c';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
  $query .= ' INNER JOIN `jobs` AS j ON (j.`instance`, j.`cluster_id`) = (c.`instance`, c.`cluster_id`)';
  $query .= sprintf(' WHERE c.`instance` = %d', $instance);
  if (count($quoted_users) != 0)
    $query .= sprintf(' AND u.`name` IN (%s)', implode(',', $quoted_users));
  if (count($quoted_cmds) != 0)
    $query .= sprintf(' AND c.`cmd` IN (%s)', implode(',', $quoted_cmds));
  if (count($quoted_ids) != 0)
    $query .= sprintf(' AND c.`cluster_id` IN (%s)', implode(',', $quoted_ids));
  if ($begin_ts != 0)
    $query .= sprintf(' AND UNIX_TIMESTAMP(c.`submit_time`) >= %d', $begin_ts);
  if ($end_ts != 0)
    $query .= sprintf(' AND UNIX_TIMESTAMP(c.`submit_time`) <= %d', $end_ts);
  $query .= ' GROUP BY c.`cluster_id`';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $user, $cmd, $timestamp, $njobs);
  $stmt->execute();
  while ($stmt->fetch())
    $data[] = array("cid" => $cid, "user" => $user, "cmd" => $cmd, "timestamp" => $timestamp, "njobs" => $njobs);
  $stmt->close();
}
else if ($_REQUEST['search'] == 'jobs') {
  $cluster_ids = $_REQUEST['clusterIds'];
  $walltime_min = 0 + $_REQUEST['wallTimeMin'];
  $walltime_max = 0 + $_REQUEST['wallTimeMax'];
  $cputime_min = 0 + $_REQUEST['cpuTimeMin'];
  $cputime_max = 0 + $_REQUEST['cpuTimeMax'];

  $data['jobs'] = array();
  $data['sites'] = array();
  $data['exitcodes'] = array();

  $query = 'SELECT c.`cluster_id`, j.`proc_id`, u.`name`, c.`cmd`, j.`match_time`, f.`frontend_alias`, CONCAT_WS(\'/\', s.`site_name`, s.`site_pool`), IF(j.`success`, \'Yes\', \'No\'), j.`cputime`, j.`walltime`, j.`exitcode`';
  $query .= ' FROM `jobs` AS j';
  $query .= ' INNER JOIN `job_clusters` AS c ON (c.`instance`, c.`cluster_id`) = (j.`instance`, j.`cluster_id`)';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
  $query .= ' LEFT JOIN `sites` AS s ON s.`site_id` = j.`site_id`';
  $query .= ' LEFT JOIN `frontends` AS f ON f.`frontend_id` = s.`frontend_id`';
  $query .= sprintf(' WHERE c.`instance` = %d', $instance);
  $query .= sprintf(' AND c.`cluster_id` IN (%s)', implode(',', $cluster_ids));
  if ($walltime_min > 0)
    $query .= sprintf(' AND j.`walltime` >= %d', $walltime_min);
  if ($walltime_max > 0)
    $query .= sprintf(' AND j.`walltime` <= %d', $walltime_max);
  if ($cputime_min > 0)
    $query .= sprintf(' AND j.`cputime` >= %d', $cputime_min);
  if ($cputime_max > 0)
    $query .= sprintf(' AND j.`cputime` <= %d', $cputime_max);

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $pid, $user, $cmd, $match_time, $frontend, $site, $success, $cputime, $walltime, $exitcode);
  $stmt->execute();
  while ($stmt->fetch()) {
    $data['jobs'][] = array("cid" => $cid,
                            "pid" => $pid,
                            "user" => $user,
                            "cmd" => $cmd,
                            "matchTime" => $match_time,
                            "frontend" => $frontend,
                            "site" => $site,
                            "success" => $success,
                            "cputime" => $cputime,
                            "walltime" => $walltime,
                            "exitcode" => $exitcode);
    if (!in_array($site, $data['sites']))
      $data['sites'][] = $site;
    if (!in_array($exitcode, $data['exitcodes']))
      $data['exitcodes'][] = $exitcode;
  }
  $stmt->close();

  sort($data['sites']);
  sort($data['exitcodes']);
}

echo json_encode($data);

?>
