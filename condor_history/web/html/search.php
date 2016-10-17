<?php

date_default_timezone_set('America/New_York');

if (!isset($_REQUEST['search']))
  exit(0);

function form_cluster_constraints($users, $cmds, $cids, $begin, $end) {
  global $db;

  $quoted_users = array();
  if (is_array($users)) {
    foreach ($users as $uid)
      $quoted_users[] = sprintf('%s', $db->real_escape_string('' . $uid));
  }
  else if ($users != '')
    $quoted_users[] = sprintf('%s', $db->real_escape_string('' . $users));

  $quoted_cmds = array();
  if (is_array($cmds)) {
    foreach ($cmds as $cmd) {
      if (strlen($cmd) != 0)
        $quoted_cmds[] = sprintf("'%s'", $db->real_escape_string($cmd));
    }
  }
  else if ($cmds != '')
    $quoted_cmds[] = sprintf("'%s'", $db->real_escape_string($cmds));

  $quoted_cids = array();
  if (is_array($cids)) {
    foreach ($cids as $cid) {
      $s = '' . $cid;
      if (strlen($s) != 0)
        $quoted_cids[] = sprintf('%s', $db->real_escape_string('' . $s));
    }
  }
  else if ('' . $cids != '')
    $quoted_cids[] = sprintf('%s', $db->real_escape_string('' . $s));

  $tm = strptime($begin, '%Y/%m/%d');
  if ($tm !== false)
    $begin_date = sprintf('%04d-%02d-%02d 00:00:00', $tm['tm_year'] + 1900, $tm['tm_mon'] + 1, $tm['tm_mday']);
  else
    $begin_date = '';

  $tm = strptime($end, '%Y/%m/%d');
  if ($tm !== false)
    $end_date = sprintf('%04d-%02d-%02d 23:59:59', $tm['tm_year'] + 1900, $tm['tm_mon'] + 1, $tm['tm_mday']);
  else
    $end_date = '';

  $query = '';

  if (count($quoted_users) != 0)
    $query .= sprintf(' AND c.`user_id` IN (%s)', implode(',', $quoted_users));
  if (count($quoted_cmds) != 0)
    $query .= sprintf(' AND c.`cmd` IN (%s)', implode(',', $quoted_cmds));
  if (count($quoted_cids) != 0)
    $query .= sprintf(' AND c.`cluster_id` IN (%s)', implode(',', $quoted_cids));
  if ($begin_date != '')
    $query .= sprintf(' AND c.`submit_time` >= \'%s\'', $begin_date);
  if ($end_date != '')
    $query .= sprintf(' AND c.`submit_time` <= \'%s\'', $end_date);

  return $query;
}

$db = new mysqli('localhost', 'condor_read', '', 'condor_history');

$stmt = $db->prepare('SELECT MAX(`instance`) FROM `job_clusters`');
$stmt->bind_result($instance);
$stmt->execute();
$stmt->fetch();
$stmt->close();

if ($_REQUEST['search'] == 'initial') {
   $data = array();

  $data['users'] = array();
  $data['frontends'] = array();

  $stmt = $db->prepare('SELECT `user_id`, `name` FROM `users` WHERE `user_id` != 0 ORDER BY `name`');
  $stmt->bind_result($uid, $name);
  $stmt->execute();
  while ($stmt->fetch())
    $data['users'][] = array('id' => $uid, 'name' => $name);
  $stmt->close();

  $stmt = $db->prepare('SELECT `frontend_id`, `frontend_alias` FROM `frontends` ORDER BY `frontend_id`');
  $stmt->bind_result($fid, $alias);
  $stmt->execute();
  while ($stmt->fetch())
    $data['frontends'][$fid] = array('id' => $fid, 'name' => $alias);
  $stmt->close();

  echo json_encode($data);
  exit(0);
}
else if ($_REQUEST['search'] == 'clusters') {
  $data = array();

  $data['many'] = false;
  $data['clusters'] = array();

  if (array_key_exists('users', $_REQUEST))
    $users = $_REQUEST['users'];
  else
    $users = array();

  if (array_key_exists('cmds', $_REQUEST))
    $cmds = $_REQUEST['cmds'];
  else
    $cmds = array();

  if (count($users) == 0 && count($cmds) == 0) {
    echo json_encode($data);
    exit(0);
  }

  if (array_key_exists('ids', $_REQUEST))
    $cids = $_REQUEST['ids'];
  else
    $cids = array();

  $begin = $_REQUEST['begin'];
  $end = $_REQUEST['end'];

  $constraints = form_cluster_constraints($users, $cmds, $cids, $begin, $end);

  $query = 'SELECT COUNT(c.`cluster_id`)';
  $query .= ' FROM `job_clusters` AS c';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
  $query .= sprintf(' WHERE c.`instance` = %d', $instance);
  $query .= $constraints;

  $stmt = $db->prepare($query);
  $stmt->bind_result($num_clusters);
  $stmt->execute();
  $stmt->fetch();
  $stmt->close();

  if ($num_clusters > 1000) {
    // too many clusters
    $data['many'] = true;
    echo json_encode($data);
    exit(0);
  }

  $query = 'SELECT c.`cluster_id`, c.`user_id`, c.`cmd`, c.`submit_time`, COUNT(j.`proc_id`)';
  $query .= ' FROM `job_clusters` AS c';
  $query .= ' INNER JOIN `jobs` AS j ON (j.`instance`, j.`cluster_id`) = (c.`instance`, c.`cluster_id`)';
  $query .= sprintf(' WHERE c.`instance` = %d', $instance);
  $query .= $constraints;
  $query .= ' GROUP BY c.`cluster_id`';
  $query .= ' ORDER BY c.`cluster_id`';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $uid, $cmd, $timestamp, $njobs);
  $stmt->execute();
  while ($stmt->fetch())
    $data['clusters'][] = array('id' => $cid, 'user' => $uid, 'cmd' => $cmd, 'timestamp' => $timestamp, 'njobs' => $njobs);
  $stmt->close();

  echo json_encode($data);
  exit(0);
}
else if ($_REQUEST['search'] == 'jobsFromClusters') {
  $data = array();

  $users = $_REQUEST['users'];
  $cmds = $_REQUEST['cmds'];

  if (count($users) == 0 && count($cmds) == 0) {
    echo '{"jobs":[],"sites":[],"exitcodes":[]}';
    exit(0);
  }

  $cids = $_REQUEST['ids'];
  $begin = $_REQUEST['begin'];
  $end = $_REQUEST['end'];

  $json = '{';

  $constraints = form_cluster_constraints($users, $cmds, $cids, $begin, $end);

  $sites_data = array();

  $query = 'SELECT DISTINCT s.`site_id`, CONCAT_WS(\'/\', s.`site_name`, s.`site_pool`) AS n, s.`frontend_id`';
  $query .= ' FROM `jobs` AS j';
  $query .= ' INNER JOIN `sites` AS s ON s.`site_id` = j.`site_id`';
  $query .= ' INNER JOIN `job_clusters` AS c ON (c.`instance`, c.`cluster_id`) = (j.`instance`, j.`cluster_id`)';
  $query .= sprintf(' WHERE j.`instance` = %d', $instance);
  $query .= $constraints;
  $query .= ' ORDER BY n';

  $stmt = $db->prepare($query);
  $stmt->bind_result($sid, $name, $fid);
  $stmt->execute();
  while ($stmt->fetch())
    $sites_data[] = '{"id":' . $sid . ',"name":"' . $name . '","frontend":' . $fid . '}';

  $json .= '"sites":[' . implode(',', $sites_data) . '],';

  $jobs_data = array();
  $codes_data = array();

  $query = 'SELECT j.`cluster_id`, j.`proc_id`, j.`match_time`, j.`site_id`, j.`cputime`, j.`walltime`, IF(j.`exitcode` IS NULL, \'null\', j.`exitcode`)';
  $query .= ' FROM `jobs` AS j';
  $query .= ' INNER JOIN `job_clusters` AS c ON (c.`instance`, c.`cluster_id`) = (j.`instance`, j.`cluster_id`)';
  $query .= sprintf(' WHERE j.`instance` = %d', $instance);
  $query .= $constraints;
  $query .= ' ORDER BY j.`cluster_id`, j.`proc_id`';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $pid, $match_time, $sid, $cputime, $walltime, $exitcode);
  $stmt->execute();
  while ($stmt->fetch()) {
    $jobs_data[] = '{"cid":' . $cid . ',"pid":' . $pid . ',"matchTime":"' . $match_time . '","site":' . $sid . ',"cputime":' . $cputime . ',"walltime":' . $walltime . ',"exitcode":' . $exitcode . ',"selected":true}';

    if (!in_array($exitcode, $codes_data))
      $codes_data[] = $exitcode;
  }
  $stmt->close();

  sort($codes_data);
  if (count($codes_data) != 0 && $codes_data[0] === 'null') {
    array_shift($codes_data);
    $codes_data[] = 'null';
  }

  $json .= '"jobs":[' . implode(',', $jobs_data) . '],';
  $json .= '"exitcodes":[' . implode(',', $codes_data) . ']';
  $json .= '}';

  echo $json;
  exit(0);
}
else if ($_REQUEST['search'] == 'jobs') {
  $cluster_ids = $_REQUEST['clusterIds'];

  if (count($cluster_ids) == 0) {
    echo '{"jobs":[],"sites":[],"exitcodes":[]}';
    exit(0);
  }

  $json = '{';

  $sites_data = array();

  $query = 'SELECT DISTINCT s.`site_id`, CONCAT_WS(\'/\', s.`site_name`, s.`site_pool`) AS n, s.`frontend_id` FROM `jobs` AS j INNER JOIN `sites` AS s ON s.`site_id` = j.`site_id`';
  $query .= sprintf(' WHERE j.`instance` = %d', $instance);
  $query .= sprintf(' AND j.`cluster_id` IN (%s)', implode(',', $cluster_ids));
  $query .= ' ORDER BY n';

  $stmt = $db->prepare($query);
  $stmt->bind_result($sid, $name, $fid);
  $stmt->execute();
  while ($stmt->fetch())
    $sites_data[] = '{"id":' . $sid . ',"name":"' . $name . '","frontend":' . $fid . '}';

  $json .= '"sites":[' . implode(',', $sites_data) . '],';

  $codes_data = array();

  $query = 'SELECT `cluster_id`, `proc_id`, `match_time`, `site_id`, `cputime`, `walltime`, IF(`exitcode` IS NULL, \'null\', `exitcode`) FROM `jobs`';
  $query .= sprintf(' WHERE `instance` = %d', $instance);
  $query .= sprintf(' AND `cluster_id` IN (%s)', implode(',', $cluster_ids));
  $query .= ' ORDER BY `cluster_id`, `proc_id`';

  $json .= '"jobs":[';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $pid, $match_time, $sid, $cputime, $walltime, $exitcode);
  $stmt->execute();
  while ($stmt->fetch()) {
    if (substr($json, -1) != '[')
      $json .= ',';
    $json .= '{"cid":' . $cid . ',"pid":' . $pid . ',"matchTime":"' . $match_time . '","site":' . $sid . ',"cputime":' . $cputime . ',"walltime":' . $walltime . ',"exitcode":' . $exitcode . ',"selected":true}';

    if (!in_array($exitcode, $codes_data))
      $codes_data[] = $exitcode;
  }
  $stmt->close();

  $json .= '],';

  sort($codes_data);
  if (count($codes_data) != 0 && $codes_data[0] === 'null') {
    array_shift($codes_data);
    $codes_data[] = 'null';
  }

  $json .= '"exitcodes":[' . implode(',', $codes_data) . ']';
  $json .= '}';

  echo $json;
  exit(0);
}

?>
