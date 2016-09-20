<?php

date_default_timezone_set('America/New_York');

if (!isset($_REQUEST['search']))
  exit(0);

function form_cluster_constraints($users, $cmds, $cids, $begin, $end) {
  global $db;

  if (is_array($users)) {
    $quoted_users = array();
    foreach ($users as $uid)
      $quoted_users[] = sprintf('%s', $db->real_escape_string('' . $uid));
  }
  else if ($users != '')
    $quoted_users = array(sprintf('%s', $db->real_escape_string('' . $users)));

  if (is_array($cmds)) {
    $quoted_cmds = array();
    foreach ($cmds as $cmd) {
      if (strlen($cmd) != 0)
        $quoted_cmds[] = sprintf("'%s'", $db->real_escape_string($cmd));
    }
  }
  else if ($cmds != '')
    $quoted_cmds = array(sprintf("'%s'", $db->real_escape_string($cmds)));

  if (is_array($cids)) {
    $quoted_cids = array();
    foreach ($cids as $cid) {
      $s = '' . $cid;
      if (strlen($s) != 0)
        $quoted_cids[] = sprintf('%s', $db->real_escape_string('' . $s));
    }
  }
  else if ('' . $cids != '')
    $quoted_cids = array(sprintf('%s', $db->real_escape_string('' . $s)));

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
    $query .= sprintf(' AND u.`user_id` IN (%s)', implode(',', $quoted_users));
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

$data = array();

if ($_REQUEST['search'] == 'initial') {
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
}
else if ($_REQUEST['search'] == 'clusters') {
  $data['many'] = false;
  $data['clusters'] = array();

  $users = $_REQUEST['users'];
  $cmds = $_REQUEST['cmds'];

  if (count($users) == 0 && count($cmds) == 0) {
    echo json_encode($data);
    exit(0);
  }

  $cids = $_REQUEST['ids'];
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

  $query = 'SELECT c.`cluster_id`, u.`user_id`, c.`cmd`, c.`submit_time`, COUNT(j.`proc_id`)';
  $query .= ' FROM `job_clusters` AS c';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
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
}
else if ($_REQUEST['search'] == 'jobsFromClusters') {
  $data['jobs'] = array();
  $data['sites'] = array();
  $data['exitcodes'] = array();

  $users = $_REQUEST['users'];
  $cmds = $_REQUEST['cmds'];

  if (count($users) == 0 && count($cmds) == 0) {
    echo json_encode($data);
    exit(0);
  }

  $cids = $_REQUEST['ids'];
  $begin = $_REQUEST['begin'];
  $end = $_REQUEST['end'];

  $constraints = form_cluster_constraints($users, $cmds, $cids, $begin, $end);

  $query = 'SELECT DISTINCT s.`site_id`, CONCAT_WS(\'/\', s.`site_name`, s.`site_pool`) AS n, s.`frontend_id`';
  $query .= ' FROM `jobs` AS j';
  $query .= ' INNER JOIN `sites` AS s ON s.`site_id` = j.`site_id`';
  $query .= ' INNER JOIN `job_clusters` AS c ON (c.`instance`, c.`cluster_id`) = (j.`instance`, j.`cluster_id`)';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
  $query .= sprintf(' WHERE j.`instance` = %d', $instance);
  $query .= $constraints;
  $query .= ' ORDER BY n';

  $stmt = $db->prepare($query);
  $stmt->bind_result($sid, $name, $fid);
  $stmt->execute();
  while ($stmt->fetch())
    $data['sites'][] = array('id' => $sid, 'name' => $name, 'frontend' => $fid);

  $query = 'SELECT j.`cluster_id`, j.`proc_id`, j.`match_time`, j.`site_id`, j.`cputime`, j.`walltime`, j.`exitcode`';
  $query .= ' FROM `jobs` AS j';
  $query .= ' INNER JOIN `job_clusters` AS c ON (c.`instance`, c.`cluster_id`) = (j.`instance`, j.`cluster_id`)';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
  $query .= sprintf(' WHERE j.`instance` = %d', $instance);
  $query .= $constraints;
  $query .= ' ORDER BY j.`cluster_id`, j.`proc_id`';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $pid, $match_time, $sid, $cputime, $walltime, $exitcode);
  $stmt->execute();
  while ($stmt->fetch()) {
    $data['jobs'][] = array('cid' => $cid,
                            'pid' => $pid,
                            'matchTime' => $match_time,
                            'site' => $sid,
                            'cputime' => $cputime,
                            'walltime' => $walltime,
                            'exitcode' => $exitcode,
                            'selected' => true
                            );

    if (!in_array($exitcode, $data['exitcodes']))
      $data['exitcodes'][] = $exitcode;
  }
  $stmt->close();

  sort($data['exitcodes']);
  if (count($data['exitcodes']) != 0 && $data['exitcodes'][0] === NULL) {
    array_shift($data['exitcodes']);
    $data['exitcodes'][] = NULL;
  }
}
else if ($_REQUEST['search'] == 'jobs') {
  $data['jobs'] = array();
  $data['sites'] = array();
  $data['exitcodes'] = array();

  $cluster_ids = $_REQUEST['clusterIds'];

  if (count($cluster_ids) == 0) {
    echo json_encode($data);
    exit(0);
  }

  $query = 'SELECT DISTINCT s.`site_id`, CONCAT_WS(\'/\', s.`site_name`, s.`site_pool`) AS n, s.`frontend_id` FROM `jobs` AS j INNER JOIN `sites` AS s ON s.`site_id` = j.`site_id`';
  $query .= sprintf(' WHERE j.`instance` = %d', $instance);
  $query .= sprintf(' AND j.`cluster_id` IN (%s)', implode(',', $cluster_ids));
  $query .= ' ORDER BY n';

  $stmt = $db->prepare($query);
  $stmt->bind_result($sid, $name, $fid);
  $stmt->execute();
  while ($stmt->fetch())
    $data['sites'][] = array('id' => $sid, 'name' => $name, 'frontend' => $fid);

  $query = 'SELECT `cluster_id`, `proc_id`, `match_time`, `site_id`, `cputime`, `walltime`, `exitcode` FROM `jobs`';
  $query .= sprintf(' WHERE `instance` = %d', $instance);
  $query .= sprintf(' AND `cluster_id` IN (%s)', implode(',', $cluster_ids));
  $query .= ' ORDER BY `cluster_id`, `proc_id`';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $pid, $match_time, $sid, $cputime, $walltime, $exitcode);
  $stmt->execute();
  while ($stmt->fetch()) {
    $data['jobs'][] = array('cid' => $cid,
                            'pid' => $pid,
                            'matchTime' => $match_time,
                            'site' => $sid,
                            'cputime' => $cputime,
                            'walltime' => $walltime,
                            'exitcode' => $exitcode,
                            'selected' => true
                            );

    if (!in_array($exitcode, $data['exitcodes']))
      $data['exitcodes'][] = $exitcode;
  }
  $stmt->close();

  sort($data['exitcodes']);
  if (count($data['exitcodes']) != 0 && $data['exitcodes'][0] === NULL) {
    array_shift($data['exitcodes']);
    $data['exitcodes'][] = NULL;
  }
}

echo json_encode($data);

?>
