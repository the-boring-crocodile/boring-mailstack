<?php
/**
 * boring-mailstack: HTML mail in dark mode.
 *
 * Elastic's dark mode shows HTML mail on white, as it was written for white.
 * This plugin, in dark mode only:
 *
 *   auto    (default) darkens HTML mail that sets no colours of its own
 *           (most personal mail: dark background, light text, dark text
 *           colours made light with their hue kept); designed mail with
 *           its own backgrounds (newsletters, receipts) stays white
 *   invert  inverts every HTML mail, pictures inverted back
 *   off     Roundcube's own: white
 *
 * The user chooses in Settings > Preferences > Displaying Messages. Light
 * mode and printing are unchanged; the mail itself is never changed.
 */
class mailstack_darkmail extends rcube_plugin
{
    public $task = 'mail|settings';

    const MODES = ['auto', 'invert', 'off'];

    function init()
    {
        $rcmail = rcmail::get_instance();

        if ($rcmail->task == 'mail' && in_array($rcmail->action, ['show', 'preview'])) {
            $mode = $this->mode();
            if ($mode != 'off') {
                $rcmail->output->set_env('mailstack_darkmail', $mode);
                $this->include_stylesheet('mailstack_darkmail.css');
                $this->include_script('mailstack_darkmail.js');
            }
        }
        elseif ($rcmail->task == 'settings') {
            $this->add_hook('preferences_list', [$this, 'preferences_list']);
            $this->add_hook('preferences_save', [$this, 'preferences_save']);
        }
    }

    function mode()
    {
        // A value written by hand or by an older version that knew other
        // modes reads as the default.
        $mode = rcmail::get_instance()->config->get('mailstack_darkmail', 'auto');
        return in_array($mode, self::MODES, true) ? $mode : 'auto';
    }

    function preferences_list($args)
    {
        if ($args['section'] != 'mailview') {
            return $args;
        }

        $this->add_texts('localization/');
        $select = new html_select(['name' => '_mailstack_darkmail', 'id' => 'rcmfd_mailstack_darkmail']);
        foreach (self::MODES as $mode) {
            $select->add($this->gettext("mode_$mode"), $mode);
        }
        $args['blocks']['main']['options']['mailstack_darkmail'] = [
            'title' => html::label('rcmfd_mailstack_darkmail', rcube::Q($this->gettext('title'))),
            'content' => $select->show($this->mode()),
        ];

        return $args;
    }

    function preferences_save($args)
    {
        if ($args['section'] == 'mailview') {
            $mode = rcube_utils::get_input_string('_mailstack_darkmail', rcube_utils::INPUT_POST);
            // Only one of the offered modes is saved; anything else leaves
            // the setting as it was.
            if (in_array($mode, self::MODES, true)) {
                $args['prefs']['mailstack_darkmail'] = $mode;
            }
        }

        return $args;
    }
}
