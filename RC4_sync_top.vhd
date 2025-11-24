library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.STD_LOGIC_ARITH.ALL;
use IEEE.STD_LOGIC_UNSIGNED.ALL;

library main_lib;


ENTITY RC4_sync_top IS 
    GENERIC (
        g_CLKS_PER_BIT : INTEGER := 870
    );
    PORT( 
        rx_serial_in : IN  STD_LOGIC;
        tx_serial_o  : OUT STD_LOGIC;
        clk_in       : IN  STD_LOGIC;
        rst_in       : IN  STD_LOGIC;
        unl_btn_in   : IN  STD_LOGIC;
        uart_state_o : OUT STD_LOGIC
    );
END ENTITY RC4_sync_top;

ARCHITECTURE struct OF RC4_sync_top IS

    SIGNAL clk_in_int           : STD_LOGIC := '0';  
    SIGNAL rst_in_int           : STD_LOGIC := '0';        
    -- SIGNAL rx_data_in_int       : STD_LOGIC_VECTOR(7 DOWNTO 0) := (others => '0');    
    SIGNAL tx_data_in_int	    : STD_LOGIC_VECTOR(7 DOWNTO 0) := (others => '0');	  
    SIGNAL rx_data_ready_in_int : STD_LOGIC := '0';    
    SIGNAL tx_requested_in_int  : STD_LOGIC := '0';	   
    SIGNAL tx_ready_in_int	   : STD_LOGIC := '0'; -- TX is ready to transmit	   
    SIGNAL encr_requested_o_int : STD_LOGIC := '0';    
    SIGNAL err_flag_o_int       : STD_LOGIC := '0';    
    SIGNAL ctrl_busy_o_int      : STD_LOGIC := '0';    
    SIGNAL unloading_ack_in_int : STD_LOGIC := '0';    
    SIGNAL tx_active_o_int      : STD_LOGIC := '0';    
    SIGNAL unload_req_o_int     : STD_LOGIC := '0';    
    SIGNAL tx_data_o_int        : STD_LOGIC_VECTOR(7 DOWNTO 0) := (others => '0');
    SIGNAL o_rx_byte_int        : STD_LOGIC_VECTOR(7 DOWNTO 0) := (others => '0');
    SIGNAL unloading_o_int      : STD_LOGIC_VECTOR(7 DOWNTO 0) := (others => '0');
    SIGNAL done_in_int          : STD_LOGIC;
    -- SIGNAL unloading_req_int    : STD_LOGIC;
    -- SIGNAL uart_data_in_int     : STD_LOGIC_VECTOR(7 DOWNTO 0);
    -- SIGNAL cipher_data_in_int   : STD_LOGIC_VECTOR(7 DOWNTO 0);
    SIGNAL uart_data_o_int      : STD_LOGIC_VECTOR(7 DOWNTO 0);
    SIGNAL RC4_data_o_int       : STD_LOGIC_VECTOR(7 DOWNTO 0);
    SIGNAL RC4_data_in_int      : STD_LOGIC_VECTOR(7 DOWNTO 0);
    SIGNAL trigger_o_int        : STD_LOGIC;
    -- SIGNAL tx_req_o_int         : STD_LOGIC;
    SIGNAL TEA_data_in_int      : STD_LOGIC_VECTOR(63 DOWNTO 0);
    SIGNAL TEA_data_o_int       : STD_LOGIC_VECTOR(63 DOWNTO 0);
    SIGNAL TEA_key_o_int        : STD_LOGIC_VECTOR(127 DOWNTO 0);
    SIGNAL tx_serial_int        : STD_LOGIC := '0'; 
    SIGNAL rx_serial_in_int     : STD_LOGIC := '1'; 
    SIGNAL tx_done_int          : STD_LOGIC := '0';
    SIGNAL rc4_req_in_int       : STD_LOGIC := '0';
    SIGNAL rc4_pln_req_i_tb     : STD_LOGIC := '0';     
    SIGNAL rc4_cip_req_i_tb     : STD_LOGIC := '0'; 

    attribute MARK_DEBUG : STRING;
    
    attribute MARK_DEBUG OF rx_serial_in_int : signal is "true";
    attribute MARK_DEBUG OF rst_in_int       : signal is "true";
    attribute MARK_DEBUG OF tx_serial_int    : signal is "true";
    
BEGIN

    rst_in_int       <= rst_in;
    rx_serial_in_int <= rx_serial_in;
    tx_serial_o      <= tx_serial_int;
    uart_state_o     <= ctrl_busy_o_int;

     UART_RX_inst: entity work.UART_RX
     generic map(
        g_CLKS_PER_BIT => g_CLKS_PER_BIT
    )
     port map(
        i_clk       => clk_in,
        i_rst       => rst_in,
        i_rx_serial => rx_serial_in_int,
        o_rx_dv     => rx_data_ready_in_int, -- TODO implement this to the controller, basically rx done, to be connected to rx_data_ready_in_int
        o_rx_byte   => o_rx_byte_int
    );

    UART_TX_inst: entity work.UART_TX
    generic map(
       g_CLKS_PER_BIT => g_CLKS_PER_BIT
   )
    port map(
         i_Clk       => clk_in,
         i_rst       => rst_in,
         i_TX_DV     => tx_active_o_int,
         i_TX_Byte   => tx_data_o_int,
         o_TX_Active => tx_ready_in_int,
         o_TX_Serial => tx_serial_int,
         o_TX_Done   => tx_done_int
   );

--uart_tx_morris_inst: entity work.uart_tx_morris
-- generic map(
--    MSG_W  => 8,
--    SMPL_W => 8
--)
-- port map(
--    i_clk       => clk_in,
--    i_rst_n     => not rst_in,
--    i_msg       => tx_data_o_int,
--    i_msg_vld   => tx_active_o_int,
--    i_start_pol => '0',
--    i_par_en    => '0',
--    i_par_type  => '0',
--    i_char_len  => "11",
--    i_clk_div   => x"0057", --X"364"/X"366"
--    o_tx        => tx_serial_int,
--    o_busy      => tx_ready_in_int,
--    o_tx_done   => tx_done_int
--);

--uart_rx_morris_inst: entity work.uart_rx_morris
-- generic map(
--    MSG_W        => 8,
--    SMPL_W       => 8
--)
-- port map(
--    i_clk            => clk_in,
--    i_rst_n          => not rst_in,
--    i_rx             => rx_serial_in_int,
--    i_start_pol      => '0',
--    i_par_en         => '0',
--    i_par_type       => '0',
--    i_char_len       => "11",
--    i_clk_div        => x"0057",
--    o_msg            => o_rx_byte_int,
--    o_msg_vld_strb   => rx_data_ready_in_int,
--    o_busy           => open,
--    o_err_noise_strb => open,
--    o_err_frame_strb => open,
--    o_err_par_strb   => open
--);


    uart_controller_inst: entity work.uart_ctrl_new
    generic map(
        G_PLN_LEN_BYTES => 255,
        G_KEY_LEN_BYTES => 255
    )
    port map(
        clk_in           => clk_in,
        rst_in           => rst_in_int,
        rx_data_in       => o_rx_byte_int,
        tx_data_in       => uart_data_o_int,
        rx_data_ready_in => rx_data_ready_in_int,
        tx_requested_in  => tx_requested_in_int,
        tx_ready_in      => not tx_ready_in_int,
        tx_done_in       => tx_done_int,
        unl_btn_in       => unl_btn_in,
        unloading_ack_in => unloading_ack_in_int,
        encr_requested_o => encr_requested_o_int,
        err_flag_o       => err_flag_o_int,
        tx_active_o      => tx_active_o_int,
        ctrl_busy_o      => ctrl_busy_o_int,
        unload_req_o     => unload_req_o_int,
        tx_data_o        => tx_data_o_int,
        unloading_o      => unloading_o_int
    );

    cipher_ctrl_inst: entity work.cipher_ctrl_new
     generic map(
        G_PLN_LEN_BYTES => 7,
        G_KEY_LEN_BYTES => 15
    )
     port map(
        clk_in         => clk_in,
        rst_in         => rst_in_int,
        rc4_pln_req_in => rc4_pln_req_i_tb,
        rc4_cip_req_in => rc4_cip_req_i_tb,
        tx_done_in     => tx_done_int,
        done_in        => done_in_int,
        unloading_req  => unload_req_o_int,
        rc4_req_in     => rc4_req_in_int,
        uart_data_in   => unloading_o_int,
        RC4_data_in    => RC4_data_in_int,
        TEA_data_in    => TEA_data_in_int,
        uart_data_o    => uart_data_o_int,
        RC4_data_o     => RC4_data_o_int,
        TEA_key_o      => TEA_key_o_int,
        TEA_data_o     => TEA_data_o_int,
        trigger_o      => trigger_o_int,
        tx_req_o       => tx_requested_in_int
    );


    -- TEA_encrypt_inst: entity work.TEA_encrypt
    --  port map(
    --     clk_in        => clk_in,
    --     rst_in        => rst_in_int,
    --     encr_start_in => trigger_o_int,
    --     data_in       => TEA_data_o_int,
    --     key_in        => TEA_key_o_int,
    --     data_o        => TEA_data_in_int,
    --     encr_done_o   => done_in_int
    -- );

  -- TEA_encrypt_click_inst: entity work.TEA_encrypt_click
  --  port map(
  --     rst        => rst_in,
  --     start      => trigger_o_int,
  --     init       => trigger_o_int,
  --     in_v0      => TEA_data_o_int(63 downto 32),
  --     in_v1      => TEA_data_o_int(31 downto 0),
  --     inKey_data => TEA_key_o_int,
  --     out_data   => TEA_data_in_int,
  --     done_o     => done_in_int
  -- );

  RC4_TOP_inst: entity work.RC4_TOP
   port map(
      clk_in             => clk_in,
      rst_in             => rst_in,
      start_in           => trigger_o_int,
      plaintext_ready_in => trigger_o_int,
      key_in             => RC4_data_o_int,
      plaintext_in       => RC4_data_o_int,
      ciphertext_o       => RC4_data_in_int,
      ciphertext_done_o  => done_in_int,
      plaintext_req_o    => open,
      ciphertext_req_o   => open,
      key_req_o          => open
  );

END ARCHITECTURE struct;