// =====================================================================
// unitree_blocks.js  —  Robot Blockly 自定义积木 + Python 生成器
//
// 覆盖:
//   - 程序开始 (unitree_setup): 网络接口 + 机器人型号, 生成 ChannelFactoryInitialize + 客户端
//   - 等待 (unitree_wait): time.sleep
//   - Go2 四足动作 (go2_*): SportClient 全部高层 API
//   - G1 人形动作 (g1_*):   LocoClient 全部高层 API
//
// 生成的 Python 代码直接对接 unitree_sdk2_python, 可由 app/code_runner.py 运行。
// =====================================================================

(function () {
  'use strict';

  // ---- 颜色 ----
  var C_COMMON = '#5ba55b';   // 绿
  var C_GO2    = '#2a7fff';   // 蓝
  var C_G1     = '#8e44ad';   // 紫

  // Python 生成器默认 2 空格缩进, 统一为 PEP8 的 4 空格
  Blockly.Python.INDENT = '    ';

  // ===================================================================
  // 工厂: 无参数动作块
  //   type, label, call, colour, tooltip, waitSec
  //   waitSec: 动作完成等待秒数。RPC 返回仅代表指令被接受, 机器人的动作
  //   (起身/趴下等) 在端上异步执行, 未等完成就发下一条会被固件忽略
  //   (教程中各动作间均有显式 time.sleep), 因此按动作补完成等待。
  // ===================================================================
  function defineActionBlock(type, label, call, colour, tooltip, waitSec) {
    Blockly.Blocks[type] = {
      init: function () {
        this.appendDummyInput().appendField(label);
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(colour);
        this.setTooltip(tooltip || (call + '()'));
        this.setHelpUrl('');
      }
    };
    Blockly.Python[type] = function () {
      Blockly.Python.definitions_['import_time'] = 'import time';
      var code = call + '\n';
      if (waitSec) {
        code += 'time.sleep(' + waitSec + ')  # 等待动作完成\n';
      }
      return code;
    };
  }

  // 工厂: 单 bool 参数动作块 (下拉 真/假)
  function defineBoolActionBlock(type, label, call, colour, tooltip, waitSec) {
    Blockly.Blocks[type] = {
      init: function () {
        this.appendDummyInput()
          .appendField(label)
          .appendField(new Blockly.FieldDropdown([
            ['真 (开启)', 'True'],
            ['假 (关闭)', 'False']
          ]), 'FLAG');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(colour);
        this.setTooltip(tooltip || (call + '(flag)'));
        this.setHelpUrl('');
      }
    };
    Blockly.Python[type] = function (block) {
      Blockly.Python.definitions_['import_time'] = 'import time';
      var flag = block.getFieldValue('FLAG');
      var code = call + '(' + flag + ')\n';
      if (waitSec) {
        code += 'time.sleep(' + waitSec + ')  # 等待设置生效\n';
      }
      return code;
    };
  }

  // ===================================================================
  // 程序开始 (hat 块) — 生成 ChannelFactoryInitialize + 客户端初始化
  // ===================================================================
  Blockly.Blocks['unitree_setup'] = {
    init: function () {
      // 机器人型号只读标签: 由顶部下拉决定, 用户不可在此切换
      var _initLabel = (typeof window !== 'undefined' && window.UNITREE_ROBOT === 'g1') ? 'G1 人形' : 'Go2 四足';
      this.appendDummyInput()
        .appendField('程序开始  机器人:')
        .appendField(new Blockly.FieldLabel(_initLabel), 'ROBOT_LABEL');
      this.setColour(C_COMMON);
      this.setTooltip('机器人型号与网络接口均由主程序顶部下拉决定, 此处不可切换');
      this.setHelpUrl('');
      this.setNextStatement(true, null);
    }
  };
  Blockly.Python['unitree_setup'] = function (block) {
    // 机器人型号由主程序顶部选择注入 (window.UNITREE_ROBOT), 此块无下拉
    var robot = 'go2';
    try { robot = window.UNITREE_ROBOT || 'go2'; } catch (e) { robot = 'go2'; }
    // 网络接口由主程序通过 window.UNITREE_IFACE 注入 (工具栏输入)
    var iface = '';
    try { iface = (window.UNITREE_IFACE || '').trim(); } catch (e) { iface = ''; }
    // 公共导入
    Blockly.Python.definitions_['import_sys']  = 'import sys';
    Blockly.Python.definitions_['import_time'] = 'import time';
    Blockly.Python.definitions_['import_channel'] =
      'from unitree_sdk2py.core.channel import ChannelFactoryInitialize';

    var initLines = '';
    if (iface) {
      initLines += 'ChannelFactoryInitialize(0, "' + iface + '")\n';
    } else {
      initLines += 'ChannelFactoryInitialize(0)\n';
    }

    if (robot === 'go2') {
      Blockly.Python.definitions_['import_json'] = 'import json';
      Blockly.Python.definitions_['import_go2_robotstate'] =
        'from unitree_sdk2py.go2.robot_state.robot_state_client import RobotStateClient';
      Blockly.Python.definitions_['import_go2_sport'] =
        'from unitree_sdk2py.go2.sport.sport_client import SportClient';
      initLines +=
        'robot_state = RobotStateClient()\n' +
        'robot_state.SetTimeout(5.0)\n' +
        'robot_state.Init()\n' +
        '# 激活 sport 服务 (固件 >=1.1.6 MCF 模式需显式开启 RPC 端点)\n' +
        'robot_state.ServiceSwitch("sport", True)\n' +
        'sport_client = SportClient()\n' +
        'sport_client.SetTimeout(10.0)\n' +
        'sport_client.Init()\n' +
        'time.sleep(1)\n';
    } else {
      // G1: 步态 LocoClient + 手臂 ArmActionClient + 音频 AudioClient
      Blockly.Python.definitions_['import_g1_loco'] =
        'from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient';
      Blockly.Python.definitions_['import_g1_arm'] =
        'from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient';
      Blockly.Python.definitions_['import_g1_audio'] =
        'from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient';
      initLines +=
        'loco_client = LocoClient()\n' +
        'loco_client.SetTimeout(10.0)\n' +
        'loco_client.Init()\n' +
        'arm_action_client = G1ArmActionClient()\n' +
        'arm_action_client.SetTimeout(10.0)\n' +
        'arm_action_client.Init()\n' +
        'audio_client = AudioClient()\n' +
        'audio_client.SetTimeout(10.0)\n' +
        'audio_client.Init()\n' +
        'time.sleep(1)\n';
    }
    return initLines;
  };

  // ===================================================================
  // 等待块
  // ===================================================================
  Blockly.Blocks['unitree_wait'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('等待')
        .appendField(new Blockly.FieldNumber(1, 0, 3600, 0.01), 'SEC')
        .appendField('秒');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_COMMON);
      this.setTooltip('生成 time.sleep(秒)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['unitree_wait'] = function (block) {
    var sec = block.getFieldValue('SEC');
    Blockly.Python.definitions_['import_time'] = 'import time';
    return 'time.sleep(' + sec + ')\n';
  };

  // 打印日志块 (用 print, 内置 text_print 也可, 这里给中文标签)
  Blockly.Blocks['unitree_print'] = {
    init: function () {
      this.appendValueInput('TEXT')
        .setCheck(null)
        .appendField('打印日志');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_COMMON);
      this.setTooltip('print(...)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['unitree_print'] = function (block) {
    var val = Blockly.Python.valueToCode(block, 'TEXT',
      Blockly.Python.ORDER_NONE) || "''";
    return 'print(' + val + ')\n';
  };

  // ===================================================================
  // Go2 动作 (SportClient)
  // ===================================================================
  defineActionBlock('go2_damp',           'Go2 阻尼趴下',      'sport_client.Damp()',            C_GO2, 'Damp() 阻尼模式', 1);
  defineActionBlock('go2_stand_up',        'Go2 站立',          'sport_client.StandUp()',         C_GO2, 'StandUp() 起身约需 3 秒', 3);
  defineActionBlock('go2_stand_down',      'Go2 趴下',          'sport_client.StandDown()',       C_GO2, 'StandDown() 趴下约需 3 秒', 3);
  defineActionBlock('go2_balance_stand',   'Go2 平衡站立',      'sport_client.BalanceStand()',    C_GO2, 'BalanceStand()', 1);
  defineActionBlock('go2_recovery_stand',  'Go2 恢复站立',      'sport_client.RecoveryStand()',   C_GO2, 'RecoveryStand() 跌倒后恢复, 约需 3 秒', 3);
  // 教程 lesson03: MCF 固件 (>=1.1.6) 上 StopMove API 未实现(返回3203),
  // 标准停止方式为发送零速度 Move(0,0,0), 停止指令生效约 0.5 秒
  defineActionBlock('go2_stop_move',       'Go2 停止移动',      'sport_client.Move(0, 0, 0)',     C_GO2, '发送零速度停止移动 (新固件上 StopMove API 未实现, 与官方教程一致用 Move(0,0,0))', 0.5);
  defineActionBlock('go2_hello',           'Go2 打招呼',        'sport_client.Hello()',           C_GO2, 'Hello()', 2);
  defineActionBlock('go2_stretch',         'Go2 伸展',          'sport_client.Stretch()',         C_GO2, 'Stretch()', 3);
  defineActionBlock('go2_heart',           'Go2 比心',          'sport_client.Heart()',           C_GO2, 'Heart()', 3);
  defineActionBlock('go2_dance1',          'Go2 舞蹈1',         'sport_client.Dance1()',          C_GO2, 'Dance1()', 6);
  defineActionBlock('go2_dance2',          'Go2 舞蹈2',         'sport_client.Dance2()',          C_GO2, 'Dance2()', 6);
  defineActionBlock('go2_front_flip',      'Go2 前空翻',        'sport_client.FrontFlip()',       C_GO2, 'FrontFlip() 高风险!', 4);
  defineActionBlock('go2_back_flip',       'Go2 后空翻',        'sport_client.BackFlip()',        C_GO2, 'BackFlip() 高风险!', 4);
  defineActionBlock('go2_left_flip',       'Go2 左空翻',        'sport_client.LeftFlip()',        C_GO2, 'LeftFlip() 高风险!', 4);
  defineActionBlock('go2_front_jump',      'Go2 前跳',          'sport_client.FrontJump()',       C_GO2, 'FrontJump()', 3);
  defineActionBlock('go2_free_walk',       'Go2 自由行走',      'sport_client.FreeWalk()',        C_GO2, 'FreeWalk() 切换步态', 0.5);
  defineActionBlock('go2_static_walk',     'Go2 静态行走',      'sport_client.StaticWalk()',      C_GO2, 'StaticWalk() 切换步态', 0.5);
  defineActionBlock('go2_trot_run',        'Go2 快步跑',        'sport_client.TrotRun()',         C_GO2, 'TrotRun() 切换步态', 0.5);

  defineBoolActionBlock('go2_pose',         'Go2 摆姿势',       'sport_client.Pose',              C_GO2, 'Pose(flag)', 1);
  defineBoolActionBlock('go2_hand_stand',  'Go2 倒立',         'sport_client.HandStand',         C_GO2, 'HandStand(flag)', 2);
  defineBoolActionBlock('go2_free_bound',  'Go2 自由蹦跳',     'sport_client.FreeBound',         C_GO2, 'FreeBound(flag)', 1);
  defineBoolActionBlock('go2_free_jump',   'Go2 自由跳',       'sport_client.FreeJump',          C_GO2, 'FreeJump(flag)', 1);
  defineBoolActionBlock('go2_free_avoid',  'Go2 自由避障',     'sport_client.FreeAvoid',         C_GO2, 'FreeAvoid(flag)', 1);
  defineBoolActionBlock('go2_walk_upright','Go2 直立行走',     'sport_client.WalkUpright',        C_GO2, 'WalkUpright(flag)', 1);
  defineBoolActionBlock('go2_cross_step',  'Go2 交叉步',       'sport_client.CrossStep',         C_GO2, 'CrossStep(flag)', 0.5);
  defineBoolActionBlock('go2_classic_walk','Go2 经典行走',     'sport_client.ClassicWalk',       C_GO2, 'ClassicWalk(flag)', 0.5);
  defineBoolActionBlock('go2_auto_recovery','Go2 自动恢复',    'sport_client.AutoRecoverySet',   C_GO2, 'AutoRecoverySet(enabled)', 0.5);

  // Go2 Move(vx, vy, vyaw, 持续秒数)
  // 教程 lesson03: 单次 Move 指令仅生效约 0.5 秒, 必须循环发送才能持续运动
  // (与官方 move_continuous 一致: 每 0.4s 重发, 结束后发零速度停止)
  Blockly.Blocks['go2_move'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('Go2 移动  vx')
        .appendField(new Blockly.FieldNumber(0.3, -2, 2, 0.05), 'VX')
        .appendField(' vy')
        .appendField(new Blockly.FieldNumber(0, -2, 2, 0.05), 'VY')
        .appendField(' 转向')
        .appendField(new Blockly.FieldNumber(0, -3, 3, 0.05), 'VYAW')
        .appendField(' 持续')
        .appendField(new Blockly.FieldNumber(2, 0.1, 3600, 0.1), 'DUR')
        .appendField('秒');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_GO2);
      this.setTooltip('先自动解锁(平衡站立)再循环发送 Move(vx, vy, vyaw) 持续指定秒数后自动停止。注意: 锁定站立状态下 Move 指令会被固件忽略');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['go2_move'] = function (block) {
    var vx = block.getFieldValue('VX');
    var vy = block.getFieldValue('VY');
    var vyaw = block.getFieldValue('VYAW');
    var dur = block.getFieldValue('DUR') || 2;
    Blockly.Python.definitions_['import_time'] = 'import time';
    var I = Blockly.Python.INDENT;
    // 实机诊断(2026-08-31): Move 必须在 BalanceStand 解锁模式下才生效,
    // 锁定站立(StandUp)状态下发送 Move 会被固件静默丢弃, 因此移动前先解锁
    return 'sport_client.BalanceStand()  # 解锁 (Move 仅在平衡站立模式下生效)\n' +
      'time.sleep(2)  # 等待解锁生效\n' +
      '_move_end = time.time() + ' + dur + '\n' +
      'while time.time() < _move_end:\n' +
      I + 'sport_client.Move(' + vx + ', ' + vy + ', ' + vyaw + ')\n' +
      I + 'time.sleep(0.4)  # 单次 Move 仅生效约 0.5 秒, 需循环发送\n' +
      'sport_client.Move(0, 0, 0)  # 停止\n' +
      'time.sleep(0.5)  # 等待停止生效\n';
  };

  // Go2 Euler(roll, pitch, yaw)
  Blockly.Blocks['go2_euler'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('Go2 姿态角  roll')
        .appendField(new Blockly.FieldNumber(0, -1.57, 1.57, 0.01), 'R')
        .appendField(' pitch')
        .appendField(new Blockly.FieldNumber(0, -1.57, 1.57, 0.01), 'P')
        .appendField(' yaw')
        .appendField(new Blockly.FieldNumber(0, -3.14, 3.14, 0.01), 'Y');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_GO2);
      this.setTooltip('Euler(roll, pitch, yaw) 调整机身姿态');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['go2_euler'] = function (block) {
    var r = block.getFieldValue('R');
    var p = block.getFieldValue('P');
    var y = block.getFieldValue('Y');
    Blockly.Python.definitions_['import_time'] = 'import time';
    return 'sport_client.Euler(' + r + ', ' + p + ', ' + y + ')\n' +
           'time.sleep(1)  # 等待姿态调整完成\n';
  };

  // Go2 SpeedLevel(level)
  Blockly.Blocks['go2_speed_level'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('Go2 速度档位')
        .appendField(new Blockly.FieldDropdown([
          ['低速', '0'], ['中速', '1'], ['高速', '2']
        ]), 'LEVEL');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_GO2);
      this.setTooltip('SpeedLevel(level)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['go2_speed_level'] = function (block) {
    var lvl = block.getFieldValue('LEVEL');
    Blockly.Python.definitions_['import_time'] = 'import time';
    return 'sport_client.SpeedLevel(' + lvl + ')\n' +
           'time.sleep(0.5)  # 等待档位切换生效\n';
  };

  // ===================================================================
  // G1 动作 (LocoClient)
  // ===================================================================
  defineActionBlock('g1_start',          'G1 启动',          'loco_client.Start()',          C_G1, 'Start() SetFsmId(500)', 2);
  defineActionBlock('g1_damp',           'G1 阻尼',          'loco_client.Damp()',           C_G1, 'Damp()', 1);
  defineActionBlock('g1_sit',            'G1 坐下',          'loco_client.Sit()',            C_G1, 'Sit()', 3);
  defineActionBlock('g1_squat2stand',    'G1 蹲→站',         'loco_client.Squat2StandUp()', C_G1, 'Squat2StandUp()', 3);
  defineActionBlock('g1_lie2stand',      'G1 躺→站',         'loco_client.Lie2StandUp()',   C_G1, 'Lie2StandUp()', 3);
  defineActionBlock('g1_stand_up2squat',  'G1 站→蹲',         'loco_client.StandUp2Squat()', C_G1, 'StandUp2Squat()', 3);
  defineActionBlock('g1_zero_torque',    'G1 零力矩',        'loco_client.ZeroTorque()',     C_G1, 'ZeroTorque()', 1);
  defineActionBlock('g1_stop_move',      'G1 停止移动',      'loco_client.StopMove()',       C_G1, 'StopMove()', 0.5);
  defineActionBlock('g1_high_stand',     'G1 高位站立',      'loco_client.HighStand()',      C_G1, 'HighStand()', 2);
  defineActionBlock('g1_low_stand',      'G1 低位站立',      'loco_client.LowStand()',       C_G1, 'LowStand()', 2);
  defineActionBlock('g1_wave_hand',      'G1 挥手',          'loco_client.WaveHand(False)', C_G1, 'WaveHand(turn=False)', 3);
  defineActionBlock('g1_wave_hand_turn', 'G1 转身挥手',      'loco_client.WaveHand(True)',  C_G1, 'WaveHand(turn=True)', 3);

  // G1 Move(vx, vy, vyaw, continuous)
  Blockly.Blocks['g1_move'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 移动  vx')
        .appendField(new Blockly.FieldNumber(0.3, -1, 1, 0.05), 'VX')
        .appendField(' vy')
        .appendField(new Blockly.FieldNumber(0, -1, 1, 0.05), 'VY')
        .appendField(' 转向')
        .appendField(new Blockly.FieldNumber(0, -2, 2, 0.05), 'VYAW')
        .appendField(' 持续')
        .appendField(new Blockly.FieldDropdown([['否', 'false'], ['是', 'true']]), 'CONT');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('Move(vx, vy, vyaw, continuous_move)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_move'] = function (block) {
    var vx = block.getFieldValue('VX');
    var vy = block.getFieldValue('VY');
    var vyaw = block.getFieldValue('VYAW');
    var cont = block.getFieldValue('CONT');
    var contPy = (cont === 'true') ? 'True' : 'False';
    return 'loco_client.Move(' + vx + ', ' + vy + ', ' + vyaw + ', ' + contPy + ')\n';
  };

  // G1 BalanceStand(mode)
  Blockly.Blocks['g1_balance_stand'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 平衡站立 模式')
        .appendField(new Blockly.FieldNumber(0, 0, 5, 1), 'MODE');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('BalanceStand(balance_mode)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_balance_stand'] = function (block) {
    var mode = block.getFieldValue('MODE');
    Blockly.Python.definitions_['import_time'] = 'import time';
    return 'loco_client.BalanceStand(' + mode + ')\n' +
           'time.sleep(1)  # 等待模式切换生效\n';
  };

  // G1 ShakeHand(stage)
  Blockly.Blocks['g1_shake_hand'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 握手 阶段')
        .appendField(new Blockly.FieldDropdown([
          ['阶段0', '0'], ['阶段1', '1'], ['交替', '-1']
        ]), 'STAGE');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('ShakeHand(stage)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_shake_hand'] = function (block) {
    var stage = block.getFieldValue('STAGE');
    Blockly.Python.definitions_['import_time'] = 'import time';
    return 'loco_client.ShakeHand(' + stage + ')\n' +
           'time.sleep(2)  # 等待动作执行\n';
  };

  // ===================================================================
  // G1 手臂动作 (G1ArmActionClient.ExecuteAction, 动作 id 来自 action_map)
  // ===================================================================
  Blockly.Blocks['g1_arm_action'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 手臂动作:')
        .appendField(new Blockly.FieldDropdown([
          ['松开手臂 (release arm)', '99'],
          ['握手 (shake hand)', '27'],
          ['击掌 (high five)', '18'],
          ['拥抱 (hug)', '19'],
          ['大幅挥手 (high wave)', '26'],
          ['鼓掌 (clap)', '17'],
          ['面部挥手 (face wave)', '25'],
          ['比心 (heart)', '20'],
          ['右比心 (right heart)', '21'],
          ['双手举 (hands up)', '15'],
          ['X 形 (x-ray)', '24'],
          ['右手举起 (right hand up)', '23'],
          ['拒绝 (reject)', '22'],
          ['左飞吻 (left kiss)', '12'],
          ['右飞吻 (right kiss)', '13'],
          ['双手飞吻 (two-hand kiss)', '11']
        ]), 'ACTION');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('arm_action_client.ExecuteAction(id) 执行预设手臂动作');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_arm_action'] = function (block) {
    var id = block.getFieldValue('ACTION');
    Blockly.Python.definitions_['import_time'] = 'import time';
    return 'arm_action_client.ExecuteAction(' + id + ')\n' +
           'time.sleep(5)  # 等待手臂动作完成\n';
  };

  // G1 释放手臂 (常用收尾动作, 独立块便于拖拽)
  defineActionBlock('g1_release_arm', 'G1 松开手臂', 'arm_action_client.ExecuteAction(99)',
    C_G1, 'ExecuteAction(99) release arm, 结束手臂动作后恢复自由', 2);

  // ===================================================================
  // G1 音频 (AudioClient)
  // ===================================================================
  // TtsMaker(text, speaker_id)
  Blockly.Blocks['g1_tts'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 语音播报')
        .appendField(new Blockly.FieldTextInput('你好'), 'TEXT')
        .appendField(' 发音人')
        .appendField(new Blockly.FieldDropdown([
          ['女声 0', '0'], ['男声 1', '1']
        ]), 'SPK');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('audio_client.TtsMaker(text, speaker_id) 文字转语音');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_tts'] = function (block) {
    var text = Blockly.Python.quote_(block.getFieldValue('TEXT'));
    var spk = block.getFieldValue('SPK');
    return 'audio_client.TtsMaker(' + text + ', ' + spk + ')\n';
  };

  // SetVolume(volume)
  Blockly.Blocks['g1_set_volume'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 音量')
        .appendField(new Blockly.FieldNumber(50, 0, 100, 1), 'VOL');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('audio_client.SetVolume(0~100)');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_set_volume'] = function (block) {
    var vol = block.getFieldValue('VOL');
    return 'audio_client.SetVolume(' + vol + ')\n';
  };

  // LedControl(R, G, B)
  Blockly.Blocks['g1_led'] = {
    init: function () {
      this.appendDummyInput()
        .appendField('G1 灯效  R')
        .appendField(new Blockly.FieldNumber(0, 0, 255, 1), 'R')
        .appendField(' G')
        .appendField(new Blockly.FieldNumber(0, 0, 255, 1), 'G')
        .appendField(' B')
        .appendField(new Blockly.FieldNumber(0, 0, 255, 1), 'B');
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(C_G1);
      this.setTooltip('audio_client.LedControl(R, G, B) 设置 RGB 灯');
      this.setHelpUrl('');
    }
  };
  Blockly.Python['g1_led'] = function (block) {
    var r = block.getFieldValue('R');
    var g = block.getFieldValue('G');
    var b = block.getFieldValue('B');
    return 'audio_client.LedControl(' + r + ', ' + g + ', ' + b + ')\n';
  };
})();
