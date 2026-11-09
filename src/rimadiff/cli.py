import rimadiff.command_history as command_history
import rimadiff.command_init_config as command_init_config
import rimadiff.command_path as command_path
import rimadiff.command_user as command_user
from rimadiff.command_rimadiff import cli


cli.add_command(command_history.history)
cli.add_command(command_user.user)
cli.add_command(command_path.path)
cli.add_command(command_init_config.init_config)
