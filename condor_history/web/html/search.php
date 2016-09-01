<?php

if (!isset($_REQUEST['search']))
  exit(0);

$db = new mysqli('localhost', 'condor_read', '', 'condor_history');

$stmt = $db->prepare('SELECT MAX(`instance`) FROM `job_clusters`');
$stmt->bind_result($instance);
$stmt->execute();
$stmt->fetch();
$stmt->close();

$data = array();

if ($_REQUEST['search'] == 'clusters') {
  $users = $_REQUEST['users'];
  $cmds = $_REQUEST['cmds'];

  if (is_array($users)) {
    $quoted_users = array();
    foreach ($users as $user)
      $quoted_users[] = sprintf("'%s'", $db->real_escape_string($user));
  }
  else if ($users != "")
    $quoted_users = array(sprintf("'%s'", $users));

  if (is_array($cmds)) {
    $quoted_cmds = array();
    foreach ($cmds as $cmd)
      $quoted_cmds[] = sprintf("'%s'", $db->real_escape_string($cmd));
  }
  else if ($cmds != "")
    $quoted_cmds = array(sprintf("'%s'", $cmds));

  $query = 'SELECT c.`cluster_id`, u.`name`, c.`cmd`, c.`submit_time`, COUNT(j.`proc_id`)';
  $query .= ' FROM `job_clusters` AS c';
  $query .= ' INNER JOIN `users` AS u ON u.`user_id` = c.`user_id`';
  $query .= ' INNER JOIN `jobs` AS j ON (j.`instance`, j.`cluster_id`) = (c.`instance`, c.`cluster_id`)';
  $query .= sprintf(' WHERE c.`instance` = %d', $instance);
  if (count($quoted_users) != 0)
    $query .= sprintf(' AND u.`name` IN (%s)', implode(',', $quoted_users));
  if (count($quoted_cmds) != 0)
    $query .= sprintf(' AND c.`cmd` IN (%s)', implode(',', $quoted_cmds));
  $query .= ' GROUP BY c.`cluster_id`';

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $user, $cmd, $timestamp, $njobs);
  $stmt->execute();
  while ($stmt->fetch())
    $data[] = array("cid" => $cid, "user" => $user, "cmd" => $cmd, "timestamp" => $timestamp, "njobs" => $njobs);

  echo json_encode($data);
}
else if ($_REQUEST['search'] == 'jobs') {
  $cluster_ids = $_REQUEST['clusterIds'];

  $query = 'SELECT `cluster_id`, `proc_id`, `match_time`, IF(`success`, \'Yes\', \'No\'), `cputime`, `walltime`, `exitcode`';
  $query .= ' FROM `jobs`';
  $query .= sprintf(' WHERE `instance` = %d', $instance);
  $query .= sprintf(' AND `cluster_id` IN (%s)', implode(',', $cluster_ids));

  $stmt = $db->prepare($query);
  $stmt->bind_result($cid, $pid, $match_time, $success, $cputime, $walltime, $exitcode);
  $stmt->execute();
  while ($stmt->fetch())
    $data[] = array("cid" => $cid,
                    "pid" => $pid,
                    "matchTime" => $match_time,
                    "success" => $success,
                    "cputime" => $cputime,
                    "walltime" => $walltime,
                    "exitcode" => $exitcode);

  echo json_encode($data);  
}

?>
