import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    RegisterEventHandler,
    SetEnvironmentVariable,
)
from launch.event_handlers import OnProcessExit
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
import random


def generate_launch_description():
    pkg_name = 'manipulator_simulator'
    pkg_share = get_package_share_directory(pkg_name)

    world_path = os.path.join(pkg_share, 'worlds', 'main_world.sdf')
    controller_config = os.path.join(pkg_share, 'config', 'manipulator_controllers.yaml')
    models_dir = os.path.join(pkg_share, 'models')
    install_share_parent = os.path.abspath(os.path.join(pkg_share, '..'))

    payload_mass = max(0,random.normalvariate(1.8, 0.4))
    print(f"\n\n\n++++++++++ Payload Attached: {payload_mass} Kg ++++++++++ \n\n\n")
    # ----------------------------------------------------
    # 1. Environment Variables for Plugins and Meshes
    # ----------------------------------------------------
    set_plugin_path = SetEnvironmentVariable(
        name='IGN_GAZEBO_SYSTEM_PLUGIN_PATH',
        value='/opt/ros/humble/lib:/opt/ros/humble/lib/ign_ros2_control:'
        + os.environ.get('IGN_GAZEBO_SYSTEM_PLUGIN_PATH', '')
    )

    set_resource_path = SetEnvironmentVariable(
        name='IGN_GAZEBO_RESOURCE_PATH',
        value=models_dir + ':' + install_share_parent + ':'
        + os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')
    )

    # ----------------------------------------------------
    # 2. Process Xacro with Parameters
    # ----------------------------------------------------
    xacro_file = PathJoinSubstitution([
        FindPackageShare(pkg_name),
        'models',
        '2dof_manipulator',
        'urdf',
        '2dof_manipulator.urdf.xacro'
    ])

    robot_description_content = Command([
        FindExecutable(name='xacro'), ' ',
        xacro_file, ' ',
        'payload_mass:=', str(payload_mass)
    ])

    robot_description = {
        'robot_description': ParameterValue(robot_description_content, value_type=str),
        'use_sim_time': True
    }

    # ----------------------------------------------------
    # 3. Start Ignition Gazebo Fortress
    # ----------------------------------------------------
    start_gazebo = ExecuteProcess(
        cmd=['ign', 'gazebo', world_path, '-r'],
        output='screen'
    )

    # ----------------------------------------------------
    # 4. Robot State Publisher Node
    # ----------------------------------------------------
    node_robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[robot_description]
    )

    # ----------------------------------------------------
    # 5. Spawn URDF Robot into Gazebo
    # ----------------------------------------------------
    spawn_entity = Node(
        package='ros_ign_gazebo',
        executable='create',
        output='screen',
        arguments=[
            '-name', '2dof_manipulator',
            '-topic', 'robot_description',
            '-x', '0.0',
            '-y', '0.0',
            '-z', '1.0',
            '-allow_renaming', 'true'
        ]
    )

    # ----------------------------------------------------
    # 6. Bridge Gazebo Force/Torque Topics to ROS 2
    # ----------------------------------------------------
    bridge_node = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        output='screen',
        arguments=[
            'FT_Sensor/joint1@geometry_msgs/msg/WrenchStamped[ignition.msgs.Wrench',
            'FT_Sensor/joint2@geometry_msgs/msg/WrenchStamped[ignition.msgs.Wrench',
            # Joint IMU sensors
            '/imu/joint1@sensor_msgs/msg/Imu[ignition.msgs.IMU',
            '/imu/joint2@sensor_msgs/msg/Imu[ignition.msgs.IMU',
        ]
    )

    # ----------------------------------------------------
    # 7. ros2_control Controller Spawners
    # ----------------------------------------------------
    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['joint_state_broadcaster'],
        output='screen'
    )

    effort_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['effort_controller', '--param-file', controller_config],
        output='screen'
    )

    delay_broadcaster = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_entity,
            on_exit=[joint_state_broadcaster_spawner]
        )
    )

    delay_effort_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[effort_controller_spawner]
        )
    )

    # delay_effort_controller = RegisterEventHandler(
    #     event_handler=OnProcessExit(
    #         target_action=spawn_entity,
    #         on_exit=[effort_controller_spawner]
    #     )
    # )

    return LaunchDescription([
        set_plugin_path,
        set_resource_path,
        start_gazebo,
        node_robot_state_publisher,
        spawn_entity,
        bridge_node,
        delay_broadcaster,
        delay_effort_controller
    ])
